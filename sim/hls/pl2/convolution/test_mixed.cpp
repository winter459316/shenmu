#include <ap_int.h>
#include <vector>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdint.h>
typedef ap_uint<256> Word;
unsigned mixed_conv(Word*,Word*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,
                    unsigned,unsigned,unsigned,unsigned,unsigned,float,float,unsigned,unsigned&);
unsigned baseline_mixed_conv(Word*,Word*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,
                    unsigned,unsigned,unsigned,unsigned,unsigned,float,float,unsigned,unsigned&);
static void set16(std::vector<Word>&m,unsigned address,int value) {
    m[address>>4].range((address&15)*16+15,(address&15)*16)=(ap_uint<16>)(ap_int<16>)value;
}
static int get16(std::vector<Word>&m,unsigned address) {
    return (int)(ap_int<16>)m[address>>4].range((address&15)*16+15,(address&15)*16);
}
static void set32(std::vector<Word>&m,unsigned address,float value) {
    union{float f;uint32_t u;}v;v.f=value;
    m[address>>4].range((address&15)*16+31,(address&15)*16)=v.u;
}
static float get32(std::vector<Word>&m,unsigned address) {
    union{float f;uint32_t u;}v;
    v.u=(uint32_t)m[address>>4].range((address&15)*16+31,(address&15)*16);return v.f;
}
static int rounded(float v,unsigned&clipped) {
    if(v>32767){clipped++;return 32767;}
    if(v<-32767){clipped++;return -32767;}
    float a=std::fabs(v);unsigned n=(unsigned)a;float frac=a-n;
    if(frac>.5f||(frac==.5f&&(n&1)))n++;
    return v<0?-(int)n:(int)n;
}
static int trial(unsigned ci,unsigned co,unsigned d,unsigned h,unsigned w,unsigned flags,
                  bool extreme=false) {
    const unsigned xo=0,wo=0x40000,yo=0x80000,po=0xc0000,ro=0xd0000;
    std::vector<Word> memory(0x100000/16);unsigned n=d*h*w,kmax=ci*27,stride=(kmax+15)&~15U;
    std::vector<int> input(ci*n),weights(co*kmax),residual(co*n);
    float rscale=.003f,inverse=flags&256?1.f:1000000.f;
    for(unsigned i=0;i<ci*n;i++){input[i]=extreme?32767:(int)((i*13+29)%2001)-1000;set16(memory,xo+i,input[i]);}
    for(unsigned m=0;m<co;m++) {
        set32(memory,po+m*2,extreme?1e-7f:1e-6f);
        set32(memory,po+64+m*2,((int)m-16)*.0125f);
        for(unsigned k=0;k<kmax;k++){
            int v=extreme?32767:(int)((k*7+m*37)%1999)-999;
            weights[m*kmax+k]=v;set16(memory,wo+m*stride+k,v);
        }
        for(unsigned i=0;i<n;i++){int v=(int)(i%101)-50;residual[m*n+i]=v;set16(memory,ro+m*n+i,v);}
    }
    std::vector<Word> baseline=memory;
    unsigned baseline_clips=0;unsigned baseline_rc=baseline_mixed_conv(baseline.data(),baseline.data(),1,xo,wo,yo,po,ro,ci,co,d,h,w,rscale,inverse,flags,baseline_clips);
    unsigned clipped=0;unsigned result=mixed_conv(memory.data(),memory.data(),1,xo,wo,yo,po,ro,
         ci,co,d,h,w,rscale,inverse,flags,clipped);
    if(result!=1||baseline_rc!=result||clipped!=baseline_clips)return 1;
    for(unsigned i=0;i<memory.size();i++)if(memory[i]!=baseline[i]){std::printf("BIT EXACT MISMATCH word %u\n",i);return 9;}
    unsigned expected_clipped=0;float maxerr=0;
    for(unsigned m=0;m<co;m++)for(unsigned z=0;z<d;z++)for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++) {
        int64_t sum=0;
        for(unsigned c=0;c<ci;c++)for(unsigned kz=0;kz<3;kz++)for(unsigned ky=0;ky<3;ky++)for(unsigned kx=0;kx<3;kx++) {
            int iz=z+kz-1,iy=y+ky-1,ix=x+kx-1;
            if(iz<0||iy<0||ix<0||iz>=(int)d||iy>=(int)h||ix>=(int)w)continue;
            unsigned k=((c*3+kz)*3+ky)*3+kx;
            sum+=(int64_t)input[((c*d+iz)*h+iy)*w+ix]*weights[m*kmax+k];
        }
        unsigned index=((m*d+z)*h+y)*w+x;
        float value=(float)sum;
        value=value*(extreme?1e-7f:1e-6f);
        value=value+((int)m-16)*.0125f;
        if(flags&16)value=value+(float)residual[index]*rscale;
        if((flags&3)==1&&value<0)value=0;
        if((flags&3)==2&&value<0)value=value*.01f;
        if(flags&256){
            float actual=get32(memory,yo+index*2);
            float err=std::fabs(actual-value);if(err>maxerr)maxerr=err;
            if(err>1e-5f*std::fmax(1.f,std::fabs(value))){std::printf("FLOAT FAIL %u %.9g %.9g\n",index,actual,value);return 2;}
        }else{
            int expected=rounded(value*inverse,expected_clipped),actual=get16(memory,yo+index);
            if(actual!=expected){std::printf("INT FAIL %u %d %d\n",index,actual,expected);return 3;}
        }
    }
    if(clipped!=expected_clipped){std::printf("CLIP FAIL %u %u\n",clipped,expected_clipped);return 4;}
    std::printf("PASS ci%u co%u %ux%ux%u flags%u extreme%d clips%u max%.8g\n",ci,co,d,h,w,flags,extreme,clipped,maxerr);
    return 0;
}
int main(int argc,char**argv){
    bool rtl=argc>1&&!std::strcmp(argv[1],"rtl");
    if(trial(1,1,1,1,16,256))return 1;
    if(trial(2,17,3,5,16,2|16))return 2;
    if(trial(2,17,3,5,80,256|2|16))return 8;
    if(rtl)return 0;
    if(trial(32,28,2,4,32,256|1|16))return 3;
    if(trial(32,32,2,4,16,256,true))return 4;
    if(trial(2,28,1,3,80,256|2))return 5;
    std::puts("MIXED_INTEGER_CSIM_PASS");return 0;
}
