#define ORT_API_MANUAL_INIT
#include "onnxruntime_cxx_api.h"
#include <sys/mman.h>
#include <sys/file.h>
#include <fcntl.h>
#include <unistd.h>
#include <chrono>
#include <cstring>
#include <cstdlib>
#include <cstdio>
#include <mutex>
#include <stdexcept>
#include <fstream>
#include <vector>
#include <arm_neon.h>
static double totals[4]={0,0,0,0},conv_totals[4]={0,0,0,0};
static double now(){using namespace std::chrono;return duration<double>(steady_clock::now().time_since_epoch()).count();}
static void fence(){asm volatile("dsb sy":::"memory");}

#include <thread>
#include <cstdlib>
// Caller owns the exclusive DMA lease and has observed completion + fence.
// Only immutable reserved-DDR output is read; no mapped lifetime escapes join.
static void dma_copy_out(void*dst,const void*src,size_t bytes){
 const char*flag=std::getenv("FAST_PL_PARALLEL_COPY");
 if(!flag||flag[0]!='1'||bytes<1048576){std::memcpy(dst,src,bytes);return;}
 size_t chunk=(bytes/4/64)*64;std::thread workers[3];unsigned started=0;
 try{
  for(unsigned i=0;i<3;i++){
   workers[i]=std::thread([=]{std::memcpy((char*)dst+i*chunk,(const char*)src+i*chunk,chunk);});started++;
  }
  std::memcpy((char*)dst+3*chunk,(const char*)src+3*chunk,bytes-3*chunk);
 }catch(...){for(unsigned i=0;i<started;i++)workers[i].join();throw;}
 for(auto &w:workers)w.join();
}
extern "C" __attribute__((visibility("default"))) void fast_pl_reorder(const float*phase_output,float*y,unsigned co,unsigned d,unsigned h,unsigned width){
 unsigned n=d*h*width;
 for(unsigned p=0;p<8;p+=2)for(unsigned c=0;c<co;c++)for(unsigned z=0;z<d;z++)for(unsigned row=0;row<h;row++){
  size_t output_row=(size_t)(c*(d*2)+z*2+((p>>2)&1))*(h*2)+row*2+((p>>1)&1);
  float *dst=y+output_row*(width*2);
  const float *lo=phase_output+(p*co+c)*n+(z*h+row)*width;
  const float *hi=lo+co*n;
  unsigned col=0;
  for(;col+4<=width;col+=4){
   float32x4x2_t pair;pair.val[0]=vld1q_f32(lo+col);pair.val[1]=vld1q_f32(hi+col);
   vst2q_f32(dst+col*2,pair);
  }
  for(;col<width;col++){dst[col*2]=lo[col];dst[col*2+1]=hi[col];}
 }
}
extern "C" __attribute__((visibility("default"))) void fast_pl_reorder_padded(const float*src,float*y,unsigned co,unsigned d,unsigned h,unsigned width){
 unsigned pitch=(width+15)&~15U,n=d*h*pitch;
 for(unsigned p=0;p<8;p+=2)for(unsigned c=0;c<co;c++)for(unsigned z=0;z<d;z++)for(unsigned row=0;row<h;row++){
  size_t output_row=(size_t)(c*(d*2)+z*2+((p>>2)&1))*(h*2)+row*2+((p>>1)&1);
  float*dst=y+output_row*(width*2);const float*lo=src+(p*co+c)*n+(z*h+row)*pitch;const float*hi=lo+co*n;
  unsigned col=0;for(;col+4<=width;col+=4){float32x4x2_t v;v.val[0]=vld1q_f32(lo+col);v.val[1]=vld1q_f32(hi+col);vst2q_f32(dst+col*2,v);}
  for(;col<width;col++){dst[col*2]=lo[col];dst[col*2+1]=hi[col];}
 }
}
extern "C" __attribute__((visibility("default"))) void fast_pl_finish_conv(const float*src,const float*bias,float*y,unsigned co,unsigned d,unsigned h,unsigned width){
 unsigned pitch=(width+15)&~15U;
 for(unsigned c=0;c<co;c++)for(unsigned row=0;row<d*h;row++){
  const float*in=src+((size_t)c*d*h+row)*pitch;float*out=y+((size_t)c*d*h+row)*width;float32x4_t b=vdupq_n_f32(bias[c]);
  unsigned x=0;for(;x+4<=width;x+=4)vst1q_f32(out+x,vaddq_f32(vld1q_f32(in+x),b));for(;x<width;x++)out[x]=in[x]+bias[c];
 }
}
struct Device{
 int fd=-1,lock=-1;float *input=nullptr,*weights=nullptr,*output=nullptr;size_t input_bytes=0,weight_bytes=0,output_bytes=0;volatile uint32_t *reg=nullptr;
 Device(){try{
  const char *enabled=std::getenv("FAST_PL_ENABLE");if(!enabled||std::strcmp(enabled,"1"))throw std::runtime_error("PL explicitly disabled");
  lock=open("/tmp/usb_stereo_probe/full_v2/dma.lock",O_CREAT|O_RDWR,0600);
  if(lock<0||flock(lock,LOCK_EX|LOCK_NB))throw std::runtime_error("Reserved DMA arena busy");
  fd=open("/dev/mem",O_RDWR|O_SYNC);if(fd<0)throw std::runtime_error("devmem open failed");
  reg=(volatile uint32_t*)mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0xA1070000);
  if(reg==MAP_FAILED)throw std::runtime_error("Control mmap failed");
  if(call(0)!=0x46445032)throw std::runtime_error("FP32 deconv IP identity mismatch");
 }catch(...){close_handles();throw;}}
 uint32_t call(unsigned cmd){
  if(!(reg[0]&4))throw std::runtime_error("FP32 deconv IP not idle");
  reg[0x18/4]=0x60000000;reg[0x68/4]=0x60000000;reg[0x20/4]=cmd;fence();reg[0]=1;fence();double end=now()+60;
  while(!(reg[0]&2)){if(now()>end){std::ofstream("/tmp/usb_stereo_probe/fast_pl/dma.fault")<<"FP32 deconv timeout; do not reuse until idle and verified reload";throw std::runtime_error("PL DMA timeout");}usleep(100);}
  fence();return reg[0x10/4];
 }
 void map_regions(size_t nx,unsigned wo,size_t nw,unsigned yo,size_t ny){
  if(input||weights||output||!nx||!nw||!ny||nx>wo||(size_t)wo+nw>yo||(size_t)yo+ny>0x07900000/4||wo%1024||yo%1024)throw std::runtime_error("Invalid reserved DMA regions");
  input_bytes=nx*4;weight_bytes=nw*4;output_bytes=ny*4;
  input=(float*)mmap(nullptr,input_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x60000000);
  weights=(float*)mmap(nullptr,weight_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x60000000ULL+(size_t)wo*4);
  output=(float*)mmap(nullptr,output_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x60000000ULL+(size_t)yo*4);
  if(input==MAP_FAILED||weights==MAP_FAILED||output==MAP_FAILED)throw std::runtime_error("Tensor DMA mmap failed");
 }
 void close_handles(){if(reg&&reg!=MAP_FAILED)munmap((void*)reg,4096);if(input&&input!=MAP_FAILED)munmap(input,input_bytes);if(weights&&weights!=MAP_FAILED)munmap(weights,weight_bytes);if(output&&output!=MAP_FAILED)munmap(output,output_bytes);if(fd>=0)close(fd);if(lock>=0)close(lock);reg=nullptr;input=weights=output=nullptr;fd=-1;lock=-1;}
 ~Device(){close_handles();}
 void compute(const float*x,const float*w,float*y,unsigned ci,unsigned co,unsigned d,unsigned h,unsigned width){
  unsigned n=d*h*width,k=ci*8;const unsigned wo=0x01000000/4,yo=0x02000000/4;
  if(ci>112||co>56||d>24||h>48||width>40||!ci||!co)throw std::runtime_error("Unsupported PL shape");
  if(!d||!h||!width||ci%2||n%16||(size_t)ci*n>wo||(size_t)8*co*k>yo-wo)throw std::runtime_error("Input/weight DMA bounds or alignment exceeded");
  unsigned pitch=width;size_t ny=(size_t)8*co*d*h*pitch;
  if((size_t)yo+ny>0x07900000/4)throw std::runtime_error("DMA bounds exceeded");
  double t=now();map_regions((size_t)ci*n,wo,(size_t)8*co*k,yo,ny);std::memcpy(input,x,ci*n*4);std::memcpy(weights,w,8*co*k*4);fence();double copied=now();
  reg[0x28/4]=0;reg[0x30/4]=wo;reg[0x38/4]=yo;
  reg[0x40/4]=ci;reg[0x48/4]=co;reg[0x50/4]=d;reg[0x58/4]=h;reg[0x60/4]=width;
  if(call(1)!=1)throw std::runtime_error("FP32 deconv IP command failed");double computed=now();
  // Bulk-copy uncached DMA memory before strided CPU tensor reordering.
  // This preserves every FP32 bit while avoiding millions of scalar device reads.
  std::vector<float> phase_output(ny);
  dma_copy_out(phase_output.data(),output,phase_output.size()*sizeof(float));
  // Phase-major DMA tensor -> original NCDHW output; no numerical transforms.
  fast_pl_reorder(phase_output.data(),y,co,d,h,width);
  double finished=now();totals[0]+=copied-t;totals[1]+=computed-copied;totals[2]+=finished-computed;totals[3]+=1;
  std::fprintf(stderr,"PL_DECONV ci=%u co=%u shape=%ux%ux%u copyin=%.6f device=%.6f copyout=%.6f\n",ci,co,d,h,width,copied-t,computed-copied,finished-computed);
 }

};
static std::mutex guard;
extern "C" __attribute__((visibility("default"))) void fast_pl_reset_stats(){std::lock_guard<std::mutex> lock(guard);for(int i=0;i<4;i++){totals[i]=0;conv_totals[i]=0;}}
struct Kernel{
 Ort::CustomOpApi api;
 Kernel(const OrtApi&a,const OrtKernelInfo*):api(a){}
 void Compute(OrtKernelContext*ctx){
  const auto*x=api.KernelContext_GetInput(ctx,0);const auto*w=api.KernelContext_GetInput(ctx,1);
  auto*xi=api.GetTensorTypeAndShape(x);auto xs=api.GetTensorShape(xi);api.ReleaseTensorTypeAndShapeInfo(xi);
  auto*wi=api.GetTensorTypeAndShape(w);auto ws=api.GetTensorShape(wi);api.ReleaseTensorTypeAndShapeInfo(wi);
  if(xs.size()!=5||xs[0]!=1||ws.size()!=3||ws[0]!=8||ws[2]!=xs[1]*8)throw std::runtime_error("Invalid deconv tensor schema");
  std::vector<int64_t> ys={1,ws[1],xs[2]*2,xs[3]*2,xs[4]*2};
  auto*y=api.KernelContext_GetOutput(ctx,0,ys.data(),ys.size());
  std::lock_guard<std::mutex> lock(guard);
  Device device;device.compute(api.GetTensorData<float>(x),api.GetTensorData<float>(w),api.GetTensorMutableData<float>(y),xs[1],ws[1],xs[2],xs[3],xs[4]);
 }
};
struct Op:Ort::CustomOpBase<Op,Kernel>{
 void*CreateKernel(const OrtApi&a,const OrtKernelInfo*i)const{return new Kernel(a,i);}
 const char*GetName()const{return "FastDeconv";}
 const char*GetExecutionProviderType()const{return "CPUExecutionProvider";}
 size_t GetInputTypeCount()const{return 2;}size_t GetOutputTypeCount()const{return 1;}
 ONNXTensorElementDataType GetInputType(size_t)const{return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;}
 ONNXTensorElementDataType GetOutputType(size_t)const{return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;}
};

// Appended to the proven FP32 deconvolution custom-op driver by build_native.py.
#include <cmath>
#include <algorithm>
#include <memory>
static double mixed_telemetry[4]={0,0,0,0};
typedef int (*MixedFallback)(const char*,const float*,float*,const int64_t*,const int64_t*);
static MixedFallback mixed_fallback=nullptr;
extern "C" __attribute__((visibility("default"))) void mixed_set_fallback(MixedFallback fn){
 std::lock_guard<std::mutex>lock(guard);mixed_fallback=fn;
}
static uint32_t fpbits(float value){uint32_t bits;std::memcpy(&bits,&value,4);return bits;}
extern "C" __attribute__((visibility("default"))) unsigned mixed_quantize(
 const float*x,int16_t*y,size_t n,float scale){
 if(!(scale>0)||!std::isfinite(scale))throw std::runtime_error("Invalid quantization scale");
 unsigned clipped=0;size_t i=0;float32x4_t s=vdupq_n_f32(scale);
 uint32x4_t clip_counts=vdupq_n_u32(0),nonfinite=vdupq_n_u32(0);
 for(;i+4<=n;i+=4){
  float32x4_t v=vdivq_f32(vld1q_f32(x+i),s);
  float32x4_t magnitude=vabsq_f32(v);
  nonfinite=vorrq_u32(nonfinite,vmvnq_u32(vcltq_f32(magnitude,vdupq_n_f32(INFINITY))));
  clip_counts=vaddq_u32(clip_counts,vshrq_n_u32(vcgtq_f32(magnitude,vdupq_n_f32(32767.f)),31));
  v=vmaxq_f32(vdupq_n_f32(-32767.f),vminq_f32(vdupq_n_f32(32767.f),v));
  vst1_s16(y+i,vqmovn_s32(vcvtnq_s32_f32(v)));
 }
 if(vmaxvq_u32(nonfinite))throw std::runtime_error("Nonfinite feature tensor");
 clipped=vaddvq_u32(clip_counts);
 for(;i<n;i++){
  float v=x[i]/scale;if(!std::isfinite(v))throw std::runtime_error("Nonfinite feature tensor");
  clipped+=v>32767.f||v<-32767.f;
  v=std::max(-32767.f,std::min(32767.f,v));y[i]=(int16_t)std::nearbyintf(v);
 }
 return clipped;
}
struct MixedDevice:Device{
 volatile uint32_t*q=nullptr;
 struct Maps {
  std::vector<std::pair<void*,size_t>>entries;
  ~Maps(){for(auto v:entries)munmap(v.first,v.second);}
  uint8_t*add(int fd,size_t offset,size_t bytes){
   if(offset%4096||!bytes||offset+bytes>0x07900000)throw std::runtime_error("Mixed arena bounds");
   void*p=mmap(nullptr,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x60000000ULL+offset);
   if(p==MAP_FAILED)throw std::runtime_error("Mixed DMA mmap failed");
   entries.push_back({p,bytes});return (uint8_t*)p;
  }
 };
 MixedDevice(){
  q=(volatile uint32_t*)mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0xA1080000);
  if(q==MAP_FAILED){q=nullptr;throw std::runtime_error("Mixed control mmap failed");}
  try{if(command(0)!=0x4d503136)throw std::runtime_error("Wrong integer IP identity");}
  catch(...){munmap((void*)q,4096);q=nullptr;throw;}
 }
 ~MixedDevice(){if(q)munmap((void*)q,4096);}
 uint32_t command(unsigned cmd){
  if(!(q[0]&4))throw std::runtime_error("Integer IP busy");
  q[0x18/4]=0x60000000;q[0x20/4]=0x60000000;q[0x28/4]=cmd;
  fence();q[0]=1;fence();double deadline=now()+60;
  while(!(q[0]&2)){
   if(now()>deadline){std::ofstream("/tmp/usb_stereo_probe/fast_pl/dma.fault")<<"Integer DMA timeout; keep arena reserved until verified idle";throw std::runtime_error("Integer IP timeout");}
   usleep(100);
  }
  fence();return q[0x10/4];
 }
 void chain(const float*x,float*y,const std::vector<const int16_t*>&weights,
  const std::vector<const float*>&params,const std::vector<unsigned>&channels,
  const float*scales,const std::vector<unsigned>&acts,bool residual,unsigned d,unsigned h,unsigned w){
  size_t n=(size_t)d*h*w;unsigned count=weights.size();
  if(!d||d>48||!h||h>96||!w||w>80||w%16||count<2||count>3||
    channels.size()!=count+1||acts.size()!=count||residual!=(count==3))
      throw std::runtime_error("Invalid integer block shape");
  unsigned maxch=*std::max_element(channels.begin(),channels.end());
  if(maxch>32)throw std::runtime_error("Integer channel limit");
  size_t span=((size_t)maxch*n*4+4095)&~4095ULL;
  unsigned slots=residual?3:2;
  if(span*slots>0x07700000)throw std::runtime_error("Integer scratch overlap");
  const size_t weight_offset=0x07700000,param_offset=0x07780000;
  Maps maps;std::vector<uint8_t*>buffer;
  double start=now();
  for(unsigned i=0;i<slots;i++)buffer.push_back(maps.add(fd,span*i,span));
  uint8_t*parameter=maps.add(fd,weight_offset,0x100000);
  std::vector<int16_t>quantized((size_t)channels[0]*n);
  unsigned input_clipped=mixed_quantize(x,quantized.data(),quantized.size(),scales[0]);
  mixed_telemetry[0]+=input_clipped;
  double quant_end=now();conv_totals[0]+=quant_end-start;
  // An out-of-range scene must use the FP32 fallback, never silently accepted.
  if(input_clipped)throw std::range_error("Mixed input exceeds calibrated range");
  std::memcpy(buffer[0],quantized.data(),quantized.size()*2);
  double copied=now();conv_totals[0]+=copied-quant_end;
  double copyin=copied-start,device=0;unsigned current=0,last=0;
  for(unsigned stage=0;stage<count;stage++){
   unsigned ci=channels[stage],co=channels[stage+1],stride=(ci*27+15)&~15U;
   if(co>32||ci>32||acts[stage]>2||!(scales[stage]>0))throw std::runtime_error("Integer parameters");
   double t=now();
   std::memcpy(parameter,weights[stage],co*stride*2);
   float values[64]={0};
   for(unsigned c=0;c<co;c++){
    values[c]=scales[stage]*params[stage][c];
    values[32+c]=params[stage][co+c];
   }
   std::memcpy(parameter+(param_offset-weight_offset),values,sizeof(values));
   fence();double parameter_seconds=now()-t;copyin+=parameter_seconds;conv_totals[0]+=parameter_seconds;
   last=residual?(stage==0?1:stage==1?2:0):1-current;
   q[0x30/4]=current*span/2;q[0x38/4]=weight_offset/2;q[0x40/4]=last*span/2;
   q[0x48/4]=param_offset/2;q[0x50/4]=span/2;
   q[0x58/4]=ci;q[0x60/4]=co;q[0x68/4]=d;q[0x70/4]=h;q[0x78/4]=w;
   q[0x80/4]=fpbits(residual?scales[1]:0);
   q[0x88/4]=fpbits(stage+1<count?1.f/scales[stage+1]:1.f);
   q[0x90/4]=acts[stage]|(residual&&stage==2?16:0)|(stage+1==count?256:0);
   t=now();if(command(1)!=1)throw std::runtime_error("Integer command rejected");
   double device_seconds=now()-t;device+=device_seconds;conv_totals[1]+=device_seconds;
   conv_totals[3]++;mixed_telemetry[3]++;
   unsigned clipped=q[0x98/4];mixed_telemetry[1]+=clipped;
   if(clipped)throw std::range_error("Mixed intermediate exceeds calibrated range");
   current=last;
  }
  double t=now();dma_copy_out(y,buffer[last],(size_t)channels.back()*n*4);double out=now()-t;
  conv_totals[2]+=out;
  std::fprintf(stderr,"MIXED_CHAIN stages=%u copyin=%.6f device=%.6f copyout=%.6f\n",count,copyin,device,out);
 }
};
struct MixedKernel{
 Ort::CustomOpApi api;std::vector<unsigned>acts;unsigned stages;bool residual;
 std::string fallback_path;
 MixedKernel(const OrtApi&a,const OrtKernelInfo*i):api(a){
  stages=api.KernelInfoGetAttribute<int64_t>(i,"stages");
  residual=api.KernelInfoGetAttribute<int64_t>(i,"residual")!=0;
  size_t count=0;Ort::ThrowOnError(a.KernelInfoGetAttributeArray_int64(i,"activations",nullptr,&count));
  std::vector<int64_t>v(count);Ort::ThrowOnError(a.KernelInfoGetAttributeArray_int64(i,"activations",v.data(),&count));
  for(auto x:v)acts.push_back(x);
  fallback_path=api.KernelInfoGetAttribute<std::string>(i,"fallback_model");
  if(stages<2||stages>3||acts.size()!=stages)throw std::runtime_error("Mixed schema");
 }
 void Compute(OrtKernelContext*ctx){
  auto*xv=api.KernelContext_GetInput(ctx,0);auto*info=api.GetTensorTypeAndShape(xv);
  auto shape=api.GetTensorShape(info);api.ReleaseTensorTypeAndShapeInfo(info);
  if(shape.size()!=5||shape[0]!=1)throw std::runtime_error("Mixed input schema");
  std::vector<const int16_t*>weights;std::vector<const float*>params;
  std::vector<unsigned>ch={unsigned(shape[1])};
  for(unsigned i=0;i<stages;i++){
   auto*w=api.KernelContext_GetInput(ctx,1+i*2),*p=api.KernelContext_GetInput(ctx,2+i*2);
   info=api.GetTensorTypeAndShape(w);auto ws=api.GetTensorShape(info);api.ReleaseTensorTypeAndShapeInfo(info);
   info=api.GetTensorTypeAndShape(p);auto ps=api.GetTensorShape(info);api.ReleaseTensorTypeAndShapeInfo(info);
   if(ws.size()!=2||ps.size()!=2||ps[0]!=2||ws[0]!=ps[1]||ws[1]!=((ch.back()*27+15)&~15U))
     throw std::runtime_error("Mixed parameter schema");
   ch.push_back(ws[0]);weights.push_back(api.GetTensorData<int16_t>(w));params.push_back(api.GetTensorData<float>(p));
  }
  auto*scale_tensor=api.KernelContext_GetInput(ctx,7);info=api.GetTensorTypeAndShape(scale_tensor);
  size_t scale_count=api.GetTensorShapeElementCount(info);api.ReleaseTensorTypeAndShapeInfo(info);
  if(scale_count!=stages)throw std::runtime_error("Mixed scale schema");
  auto output_shape=shape;output_shape[1]=ch.back();
  auto*out=api.KernelContext_GetOutput(ctx,0,output_shape.data(),output_shape.size());
  const float*x=api.GetTensorData<float>(xv);float*y=api.GetTensorMutableData<float>(out);
  std::lock_guard<std::mutex>lock(guard);
  try{
   MixedDevice dev;dev.chain(x,y,weights,params,ch,api.GetTensorData<float>(scale_tensor),
                           acts,residual,shape[2],shape[3],shape[4]);
  }catch(const std::range_error&){
   // Device is finished and RAII has released every mapping/lease before CPU fallback.
   mixed_telemetry[2]++;
   // Reuse the Python host's ORT environment; creating a second default Env
   // inside a Python-hosted custom operator conflicts with ORT's log manager.
   if(!mixed_fallback||mixed_fallback(fallback_path.c_str(),x,y,shape.data(),output_shape.data()))
    throw std::runtime_error("PS FP32 range fallback failed; inspect host callback log");
   std::fprintf(stderr,"MIXED_FP32_RANGE_FALLBACK %s\n",fallback_path.c_str());
  }
 }
};
struct MixedOp:Ort::CustomOpBase<MixedOp,MixedKernel>{
 void*CreateKernel(const OrtApi&a,const OrtKernelInfo*i)const{return new MixedKernel(a,i);}
 const char*GetName()const{return "MixedChain";}
 const char*GetExecutionProviderType()const{return "CPUExecutionProvider";}
 size_t GetInputTypeCount()const{return 8;}size_t GetOutputTypeCount()const{return 1;}
 ONNXTensorElementDataType GetInputType(size_t i)const{
  return i==1||i==3||i==5?ONNX_TENSOR_ELEMENT_DATA_TYPE_INT16:ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
 }
 ONNXTensorElementDataType GetOutputType(size_t)const{return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;}
};
extern "C" __attribute__((visibility("default"))) OrtStatus* RegisterCustomOps(OrtSessionOptions* options,const OrtApiBase*base){
 const OrtApi*api=base->GetApi(ORT_API_VERSION);Ort::InitApi(api);
 static Op op;static MixedOp mixed;static OrtCustomOpDomain*fp=nullptr,*integer=nullptr;
 if(!fp){
  OrtStatus*s=api->CreateCustomOpDomain("fastpl",&fp);if(s)return s;
  s=api->CustomOpDomain_Add(fp,&op);if(s)return s;
  s=api->CreateCustomOpDomain("mixedpl",&integer);if(s)return s;
  s=api->CustomOpDomain_Add(integer,&mixed);if(s)return s;
 }
 OrtStatus*s=api->AddCustomOpDomain(options,fp);if(s)return s;
 return api->AddCustomOpDomain(options,integer);
}
extern "C" __attribute__((visibility("default"))) void fast_pl_stats(double*out){std::memcpy(out,totals,sizeof(totals));}
extern "C" __attribute__((visibility("default"))) void fast_conv_stats(double*out){std::memcpy(out,conv_totals,sizeof(conv_totals));}
extern "C" __attribute__((visibility("default"))) void mixed_stats(double*out){std::memcpy(out,mixed_telemetry,sizeof(mixed_telemetry));}
extern "C" __attribute__((visibility("default"))) void mixed_reset_stats(){
 std::lock_guard<std::mutex>lock(guard);
 for(int i=0;i<4;i++){totals[i]=0;conv_totals[i]=0;mixed_telemetry[i]=0;}
}
