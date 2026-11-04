#include <ap_int.h>
#include <cstdio>
#include <vector>
#include <cassert>
#include <cstring>
typedef ap_uint<128> word;
unsigned preview_filters(word*,word*,unsigned,unsigned,unsigned);
int main(int argc,char**argv){
    int count=(argc>1&&std::strcmp(argv[1],"rtl")==0)?2:3;
    const int widths[]={16,32,1280},heights[]={8,17,480};
    for(int sample=0;sample<count;sample++){
        unsigned n=widths[sample]*heights[sample];std::vector<word> in(153600),out(38401);
        char file[80];std::sprintf(file,"in%d.bin",sample);FILE*f=std::fopen(file,"rb");assert(f);
        for(unsigned i=0;i<n/4;i++)for(int j=0;j<16;j++){int b=std::fgetc(f);assert(b>=0);in[i].range(8*j+7,8*j)=b;}std::fclose(f);
        assert(preview_filters(in.data(),out.data(),0,0,0)==0x50464C31);
        assert(preview_filters(in.data(),out.data(),1,15,2)==0);
        for(unsigned mode=1;mode<=3;mode++){
            out[n/16]=0xdeadbeef;assert(preview_filters(in.data(),out.data(),mode,widths[sample],heights[sample])==1);
            assert(out[n/16]==0xdeadbeef);std::sprintf(file,"out%d_%d.bin",sample,mode);f=std::fopen(file,"rb");assert(f);
            for(unsigned i=0;i<n;i++){int b=std::fgetc(f);unsigned v=out[i/16].range((i%16)*8+7,(i%16)*8).to_uint();if(b!=int(v)){std::printf("MISMATCH sample=%d mode=%u i=%u expected=%d actual=%u\n",sample,mode,i,b,v);return 1;}}std::fclose(f);
            std::printf("EXACT sample=%d mode=%u pixels=%u\n",sample,mode,n);
        }
    }
    return 0;
}
