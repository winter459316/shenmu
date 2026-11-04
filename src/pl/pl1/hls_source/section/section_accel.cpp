#include <ap_int.h>
#include <hls_stream.h>
#include <hls_math.h>
#include <stdint.h>
#define N 512
struct Seg {float x0,y0,x1,y1; bool valid;};
// Parameters: plane n,d; in-plane u,v; lower u,v and scale to 512 pixels.
static void extract(const float *tri, unsigned count, const float p[16], hls::stream<Seg>& stream){
    for(unsigned t=0;t<count;t++){
#pragma HLS PIPELINE II=9
        float a[3][3],d[3],q[2][3];
#pragma HLS ARRAY_PARTITION variable=a complete
#pragma HLS ARRAY_PARTITION variable=d complete
#pragma HLS ARRAY_PARTITION variable=q complete
        for(int i=0;i<3;i++)for(int j=0;j<3;j++)a[i][j]=tri[t*9+i*3+j];
        for(int i=0;i<3;i++)d[i]=(a[i][0]*p[0]+a[i][1]*p[1])+a[i][2]*p[2]+p[3];
        int k=0;
        for(int i=0;i<3;i++){
            int j=i==2?0:i+1;
            if((d[i]<0)!=(d[j]<0)){
                float f=d[i]/(d[i]-d[j]);
                for(int z=0;z<3;z++)q[k][z]=a[i][z]+f*(a[j][z]-a[i][z]);
                k++;
            }
        }
        Seg s;s.valid=k==2;s.x0=s.y0=s.x1=s.y1=0;
        if(s.valid){
            s.x0=(((q[0][0]*p[4]+q[0][1]*p[5])+q[0][2]*p[6])-p[10])*p[12];
            s.y0=(((q[0][0]*p[7]+q[0][1]*p[8])+q[0][2]*p[9])-p[11])*p[12];
            s.x1=(((q[1][0]*p[4]+q[1][1]*p[5])+q[1][2]*p[6])-p[10])*p[12];
            s.y1=(((q[1][0]*p[7]+q[1][1]*p[8])+q[1][2]*p[9])-p[11])*p[12];
        }
        stream.write(s);
    }
}
static void fill(hls::stream<Seg>& stream,unsigned count,uint32_t*out,bool boundsOnly){
    ap_uint<32> crossings[N][N/32];
#pragma HLS RESOURCE variable=crossings core=RAM_T2P_BRAM
    for(int y=0;y<N;y++)for(int x=0;x<N/32;x++){
#pragma HLS PIPELINE II=1
        crossings[y][x]=0;
    }
    unsigned segments=0,hits=0;float xmin=1e30f,ymin=1e30f,xmax=-1e30f,ymax=-1e30f;
    for(unsigned t=0;t<count;t++){
        Seg s=stream.read();
        if(!s.valid)continue;
        xmin=hls::fminf(xmin,hls::fminf(s.x0,s.x1));xmax=hls::fmaxf(xmax,hls::fmaxf(s.x0,s.x1));
        ymin=hls::fminf(ymin,hls::fminf(s.y0,s.y1));ymax=hls::fmaxf(ymax,hls::fmaxf(s.y0,s.y1));
        segments++;
        if(boundsOnly||s.y0==s.y1)continue;
        if(s.y0>s.y1){float v=s.x0;s.x0=s.x1;s.x1=v;v=s.y0;s.y0=s.y1;s.y1=v;}
        float slope=(s.x1-s.x0)/(s.y1-s.y0);
        int first=(int)hls::ceilf(s.y0-0.5f),last=(int)hls::ceilf(s.y1-0.5f);
        if(first<0)first=0;if(last>N)last=N;
        for(int y=first;y<last;y++){
#pragma HLS PIPELINE II=4
            float x=s.x0+((float)y+0.5f-s.y0)*slope;
            int ix=(int)hls::ceilf(x-0.5f);if(ix<0)ix=0;
            if(ix<N){crossings[y][ix>>5]^=ap_uint<32>(1)<<(ix&31);hits++;}
        }
    }
    unsigned pixels=0,bad_rows=0;
    if(!boundsOnly)for(int y=0;y<N;y++){
        bool parity=false;
        for(int w=0;w<N/32;w++){
            ap_uint<32> bits=crossings[y][w];
            for(int b=0;b<32;b++){
#pragma HLS PIPELINE II=1
                parity^=bits[b];out[16+y*N+w*32+b]=parity?255:0;pixels+=parity;
            }
        }
        bad_rows+=parity;
    }
    out[0]=0x53454331;out[1]=count;out[2]=segments;out[3]=pixels;out[4]=bad_rows;out[5]=hits;
    union Bits{float f;uint32_t u;}b;
    b.f=xmin;out[6]=b.u;b.f=ymin;out[7]=b.u;b.f=xmax;out[8]=b.u;b.f=ymax;out[9]=b.u;
}
static void compute(const float*tri,uint32_t*out,unsigned count,float p[16],bool boundsOnly){
#pragma HLS DATAFLOW
    hls::stream<Seg> stream;
#pragma HLS STREAM variable=stream depth=64
    extract(tri,count,p,stream);fill(stream,count,out,boundsOnly);
}
extern "C" unsigned section_accel(const float*tri,const float*params,uint32_t*out,unsigned count,unsigned command){
#pragma HLS INTERFACE m_axi port=tri offset=slave bundle=readmem depth=4500000 max_read_burst_length=64 num_read_outstanding=8
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=readmem depth=16
#pragma HLS INTERFACE m_axi port=out offset=slave bundle=writemem depth=262160 max_write_burst_length=64 num_write_outstanding=8
#pragma HLS INTERFACE s_axilite port=tri bundle=control
#pragma HLS INTERFACE s_axilite port=params bundle=control
#pragma HLS INTERFACE s_axilite port=out bundle=control
#pragma HLS INTERFACE s_axilite port=count bundle=control
#pragma HLS INTERFACE s_axilite port=command bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if(command==0)return 0x53454331;
    if((command!=1&&command!=2)||count>500000)return 0xFFFFFFFF;
    float p[16];
#pragma HLS ARRAY_PARTITION variable=p complete
    for(int i=0;i<16;i++)p[i]=params[i];
    compute(tri,out,count,p,command==2);return 0;
}
