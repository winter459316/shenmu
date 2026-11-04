#include <ap_int.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
typedef ap_uint<128> word;
unsigned preview_extra(word*,word*,ap_uint<64>*,unsigned,unsigned,unsigned);
static void load(const char*n,void*p,size_t bytes){FILE*f=fopen(n,"rb");if(!f||fread(p,1,bytes,f)!=bytes){printf("READ_FAIL %s\n",n);exit(2);}fclose(f);}
int main(int argc,char**argv){
    static word in[153600],out[153600];static ap_uint<64> maps[230400];
    std::vector<unsigned char> bytes(2457600),expected(2457600);std::vector<unsigned long long> m(230400);
    if(argc>1 && strcmp(argv[1],"rtl")==0){
        for(int sample=3;sample<=4;sample++){
            char name[64];sprintf(name,"in%d.bin",sample);load(name,&bytes[0],6144);
            for(int i=0;i<384;i++)for(int k=0;k<16;k++)in[i].range(k*8+7,k*8)=bytes[i*16+k];
            sprintf(name,"vessel%d.bin",sample);load(name,&expected[0],6144);
            if(preview_extra(in,out,maps,5,64,24)!=1)return 6;
            for(int i=0;i<6144;i++)if(out[i/16].range((i%16)*8+7,(i%16)*8)!=expected[i]){printf("RTL_DIFF %d %d\n",sample,i);return 7;}
        }
        puts("VESSEL_RTL_EXACT");return 0;
    }
    load("maps.bin",&m[0],1843200);for(int i=0;i<230400;i++)maps[i]=m[i];
    if(preview_extra(in,out,maps,0,0,0)!=0x50585031)return 3;
    for(int sample=0;sample<(argc>1?2:1);sample++)for(int cmd=1;cmd<=5;cmd++){
        char name[64];sprintf(name,"in%d.bin",sample);load(name,&bytes[0],2457600);
        for(int i=0;i<153600;i++)for(int k=0;k<16;k++)in[i].range(k*8+7,k*8)=bytes[i*16+k];
        const char*names[]={"","tone","rect","guide","meter","vessel"};sprintf(name,"%s%d.bin",names[cmd],sample);
        size_t n=cmd==2?921600:(cmd==4?80:2457600);load(name,&expected[0],n);
        if(preview_extra(in,out,maps,cmd,1280,480)!=1)return 4;
        unsigned errors=0;for(size_t i=0;i<n;i++){unsigned got=out[i/16].range((i%16)*8+7,(i%16)*8);if(got!=expected[i]){if(errors<8)printf("DIFF sample=%d cmd=%d byte=%u got=%u expected=%u\n",sample,cmd,(unsigned)i,got,expected[i]);errors++;}}
        printf("CASE %d %d errors=%u\n",sample,cmd,errors);if(errors)return 5;
    }
    load("in2.bin",&bytes[0],2457600);load("vessel2.bin",&expected[0],2457600);
    for(int i=0;i<153600;i++)for(int k=0;k<16;k++)in[i].range(k*8+7,k*8)=bytes[i*16+k];
    if(preview_extra(in,out,maps,5,1280,480)!=1)return 8;
    for(int i=0;i<2457600;i++)if(out[i/16].range((i%16)*8+7,(i%16)*8)!=expected[i])return 9;
    puts("EXTRA_ALL_EXACT");return 0;
}
