// Specialized FP32 GridSample for H=1, align_corners=1, bilinear, zero padding.
// Semantics checked against ONNX Runtime 1.14.1 grid_sample.cc (MIT).
#define ORT_API_MANUAL_INIT
#include "onnxruntime_cxx_api.h"
#include <cmath>
#include <vector>
#include <thread>
#include <stdexcept>
#include <algorithm>
struct SampleKernel {
 Ort::CustomOpApi api;
 SampleKernel(const OrtApi&a,const OrtKernelInfo*):api(a){}
 void Compute(OrtKernelContext*ctx) {
  auto xv=api.KernelContext_GetInput(ctx,0),gv=api.KernelContext_GetInput(ctx,1);
  auto ti=api.GetTensorTypeAndShape(xv);auto xs=api.GetTensorShape(ti);api.ReleaseTensorTypeAndShapeInfo(ti);
  ti=api.GetTensorTypeAndShape(gv);auto gs=api.GetTensorShape(ti);api.ReleaseTensorTypeAndShapeInfo(ti);
  if(xs.size()!=4||gs.size()!=4||xs[2]!=1||gs[0]!=xs[0]||gs[3]!=2||gs[1]!=1||gs[2]>64||xs[3]<1)throw std::runtime_error("Sample1D shape");
  int64_t N=xs[0],C=xs[1],W=xs[3],K=gs[2];
  const float*x=api.GetTensorData<float>(xv),*g=api.GetTensorData<float>(gv);
  // Reject malformed grids before workers; no exception can escape a thread.
  for(int64_t i=0;i<N*K*2;i++)if(!std::isfinite(g[i]))throw std::runtime_error("Sample1D nonfinite grid");
  int64_t ys[4]={N,C,1,K};auto out=api.KernelContext_GetOutput(ctx,0,ys,4);float*y=api.GetTensorMutableData<float>(out);
  auto work=[&](int64_t begin,int64_t end){
   for(int64_t n=begin;n<end;n++){
    int64_t lo[64],hi[64];float a[64],b[64];
    for(int64_t k=0;k<K;k++){
     float pos=(g[(n*K+k)*2]+1.f)/2.f*float(W-1);
     // Outside both support pixels: zero padding; avoid overflowing integer conversion.
     if(pos<=-1.f||pos>=float(W)){lo[k]=hi[k]=-1;a[k]=1.f;b[k]=0.f;continue;}
     int64_t i=int64_t(std::floor(pos));lo[k]=i>=0?i:-1;hi[k]=i+1<W?i+1:-1;
     a[k]=float(i+1)-pos;b[k]=pos-float(i);
    }
    for(int64_t c=0;c<C;c++){
     const float*row=x+(n*C+c)*W;float*dst=y+(n*C+c)*K;
     for(int64_t k=0;k<K;k++){
      float p=lo[k]>=0?row[lo[k]]:0.f,q=hi[k]>=0?row[hi[k]]:0.f;
      dst[k]=std::fma(a[k],p,b[k]*q);
     }
    }
   }
  };
  if(N<256){work(0,N);return;}
  std::thread t[3];unsigned started=0;
  try {for(unsigned i=0;i<3;i++){t[i]=std::thread(work,N*i/4,N*(i+1)/4);started++;}work(N*3/4,N);}
  catch(...){for(unsigned i=0;i<started;i++)t[i].join();throw;}
  for(auto &w:t)w.join();
 }
};
struct SampleOp:Ort::CustomOpBase<SampleOp,SampleKernel>{
 void*CreateKernel(const OrtApi&a,const OrtKernelInfo*i)const{return new SampleKernel(a,i);}
 const char*GetName()const{return "Sample1D";}
 const char*GetExecutionProviderType()const{return "CPUExecutionProvider";}
 size_t GetInputTypeCount()const{return 2;}size_t GetOutputTypeCount()const{return 1;}
 ONNXTensorElementDataType GetInputType(size_t)const{return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;}
 ONNXTensorElementDataType GetOutputType(size_t)const{return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;}
};
extern "C" __attribute__((visibility("default"))) OrtStatus*RegisterCustomOps(OrtSessionOptions*options,const OrtApiBase*base){
 auto api=base->GetApi(ORT_API_VERSION);Ort::InitApi(api);static SampleOp op;static OrtCustomOpDomain*d=nullptr;
 if(!d){auto s=api->CreateCustomOpDomain("fastcpu",&d);if(s)return s;s=api->CustomOpDomain_Add(d,&op);if(s)return s;}
 return api->AddCustomOpDomain(options,d);
}
