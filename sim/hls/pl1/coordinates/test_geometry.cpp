#include <ap_int.h>
#include <stdint.h>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <vector>
typedef ap_uint<128> Word;
unsigned fast_geometry(Word*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned&);
static uint32_t bits(float f){union{uint32_t u;float f;}v;v.f=f;return v.u;}
static uint64_t bits64(double d){union{uint64_t u;double d;}v;v.d=d;return v.u;}
static float f32(uint32_t u){union{uint32_t u;float f;}v;v.u=u;return v.f;}
static void params(std::vector<Word>&m,const double*q){
 for(unsigned i=0;i<8;i++){Word w=0;w.range(63,0)=bits64(q[2*i]);w.range(127,64)=bits64(q[2*i+1]);m[i]=w;}
}
static int small(){
 const unsigned w=32,h=4,io=16,oo=100;std::vector<Word> m(4096);
 double q[16]={2,0,0,-300.600555,0,1.3333333333333333,0,-250.034118,0,0,0,347.282566,0,0,.0332897794,.002};
 params(m,q);float special[]={0,-1,1e-30f,1.f,4.1234567f,63.987654f,191.99998f,f32(0x7f800000U),f32(0x7fc00000U)};
 unsigned expected_count=0;
 for(unsigned i=0;i<w*h;i++){
  float d=special[i%9];ap_uint<64> r=bits(d);r[32]=(i%11)!=0;
  m[io+i/2].range((i%2)*64+63,(i%2)*64)=r;
 }
 unsigned count=123;
 if(fast_geometry(m.data(),0,w,h,io,oo,count)!=0x46475031U)return 1;
 if(count!=0)return 19;
 if(fast_geometry(m.data(),1,w,h,io,oo,count)!=1)return 2;
 for(unsigned i=0;i<w*h;i++){
  float d=special[i%9];unsigned x=i%w,y=i/w;
  double den=q[14]*(double)d+q[15];
  float a[3]={(float)((q[0]*(double)x+q[3])/den),(float)((q[5]*(double)y+q[7])/den),(float)(q[11]/den)};
  bool v=(i%11)!=0&&std::isfinite(d)&&d>0&&std::isfinite(a[0])&&std::isfinite(a[1])&&std::isfinite(a[2])&&a[2]>0;
  if((unsigned)m[oo+i].range(127,96)!=(unsigned)v)return 3;
  for(unsigned j=0;j<3;j++){
   uint32_t got=m[oo+i].range(j*32+31,j*32);
   if(got!=(v?bits(a[j]):0x7fc00000U)){std::printf("DIFF %u %u %08x %08x\n",i,j,got,bits(a[j]));return 4;}
  }
  expected_count+=v;
 }
 if(count!=expected_count){std::printf("COUNT %u expected %u\n",count,expected_count);return 5;}
 q[1]=1;params(m,q);if(fast_geometry(m.data(),1,w,h,io,oo,count)!=0)return 6;
 std::puts("GEOMETRY_SMALL_EXACT_PASS");return 0;
}
static int full(){
 FILE*f=std::fopen("test_q.bin","rb");if(!f)return 10;double q[16];if(std::fread(q,8,16,f)!=16)return 11;std::fclose(f);
 const unsigned n=320*360,io=16,oo=65536;std::vector<Word>m(300000);params(m,q);
 f=std::fopen("test_input.bin","rb");if(!f)return 12;
 for(unsigned i=0;i<n;i++){uint64_t r;if(std::fread(&r,8,1,f)!=1)return 13;m[io+i/2].range((i%2)*64+63,(i%2)*64)=r;}std::fclose(f);
 unsigned count=0;if(fast_geometry(m.data(),1,320,360,io,oo,count)!=1)return 14;
 f=std::fopen("test_expected.bin","rb");if(!f)return 15;unsigned expected=0;
 for(unsigned i=0;i<n;i++){
  uint32_t a[4];if(std::fread(a,4,4,f)!=4)return 16;expected+=a[3];
  for(unsigned j=0;j<4;j++)if((uint32_t)m[oo+i].range(j*32+31,j*32)!=a[j]){std::printf("FULL DIFF %u %u\n",i,j);return 17;}
 }
 std::fclose(f);if(count!=expected)return 18;
 std::printf("GEOMETRY_FULL_EXACT_PASS points%u valid%u\n",n,count);return 0;
}
int main(int argc,char**argv){int r=small();if(r)return r;if(argc>1&&!std::strcmp(argv[1],"rtl"))return 0;return full();}
