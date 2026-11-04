// Independent INT16 convolution engine: 256 integer MAC lanes, exact INT48 sum.
// Input/weight/intermediate tensors are signed INT16; final block output FP32.
// A second FP32 deconvolution engine is retained separately by the PS scheduler.
#include <ap_int.h>
#include <stdint.h>

typedef ap_uint<256> Word;
typedef ap_int<16> I16;
typedef ap_int<48> Acc;

static unsigned volume(unsigned d,unsigned h,unsigned w) {
#pragma HLS INLINE
    ap_uint<14> plane=((ap_uint<7>)h)*((ap_uint<7>)w);
    ap_uint<20> n=plane*((ap_uint<6>)d);
    return n;
}
static unsigned position(unsigned c,unsigned z,unsigned y,unsigned x,
                         unsigned d,unsigned h,unsigned w) {
#pragma HLS INLINE
    ap_uint<25> channel=((ap_uint<6>)c)*((ap_uint<20>)volume(d,h,w));
    ap_uint<14> row=((ap_uint<6>)z)*((ap_uint<7>)h)+((ap_uint<7>)y);
    ap_uint<21> pixel=row*((ap_uint<7>)w)+((ap_uint<7>)x);
    ap_uint<26> index=channel+pixel;
    return index;
}
static float as_float(ap_uint<32> bits) {
#pragma HLS INLINE
    union { uint32_t u; float f; } v;
    v.u = bits; return v.f;
}
static ap_uint<32> as_bits(float f) {
#pragma HLS INLINE
    union { uint32_t u; float f; } v;
    v.f = f; return v.u;
}
static I16 get16(Word word, unsigned j) {
#pragma HLS INLINE
    return (ap_int<16>)word.range(j*16+15, j*16);
}
static float get32(Word word, unsigned j) {
#pragma HLS INLINE
    return as_float(word.range(j*32+31, j*32));
}
static I16 nearest_even(float value, unsigned &clipped) {
#pragma HLS INLINE
    if (value > 32767.f) { clipped++; return 32767; }
    if (value < -32767.f) { clipped++; return -32767; }
    bool negative = value < 0;
    float a = negative ? -value : value;
    unsigned integer = (unsigned)a;
    float fraction = a - (float)integer;
    if (fraction > .5f || (fraction == .5f && (integer & 1))) integer++;
    return negative ? -(int)integer : (int)integer;
}
static void origin(unsigned tile, unsigned height, unsigned width,
                   unsigned &z, unsigned &y, unsigned &x) {
#pragma HLS INLINE
    ap_uint<3> bw = ((ap_uint<7>)width)/16;
    ap_uint<5> bh = (((ap_uint<7>)height)+3)/4;
    ap_uint<12> index=tile;
    ap_uint<7> plane=bw*bh;
    x = (index % bw)*16; y = ((index/bw)%bh)*4; z = (index/plane)*2;
}
static void weights_load(Word *memory, I16 weights[16][2048], unsigned woff,
                         unsigned ci, unsigned co) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=weights complete dim=1
    unsigned kmax = ci*27, stride = (kmax+15)&~15U;
    for (unsigned m=0; m<co; m++) {
        for (unsigned k=0; k<stride; k+=16) {
            Word line = memory[(woff + m*stride + k)>>4];
            for (unsigned j=0; j<16; j++) {
#pragma HLS PIPELINE II=1
                if (k+j < kmax)
                    weights[m&15][(m>>4)*1024+k+j] = get16(line,j);
            }
        }
    }
}
static void patch_load(Word *memory, I16 patch[16][2048], unsigned tile,
                       unsigned xoff, unsigned ci, unsigned depth,
                       unsigned height, unsigned width) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=patch complete dim=1
    // Adjacent x tiles share two of their three aligned DDR words.
    // First tile of every row primes every used cache entry; command shape
    // changes always restart at x0=0, so no prior-command data is consumed.
    static Word last_b[768],last_d[768];
#pragma HLS RESOURCE variable=last_b core=XPM_MEMORY uram
#pragma HLS RESOURCE variable=last_d core=XPM_MEMORY uram
    unsigned z0,y0,x0; origin(tile,height,width,z0,y0,x0);
    unsigned n=volume(depth,height,width);
    for (unsigned c=0;c<ci;c++) for (unsigned dz=0;dz<4;dz++)
        for (unsigned dy=0;dy<6;dy++) {
#pragma HLS PIPELINE II=4
            int z=(int)z0+(int)dz-1, y=(int)y0+(int)dy-1;
            int base=(int)xoff+(int)position(c,z,y,x0,depth,height,width)-1;
            int wi=base>>4; unsigned shift=(base&15)*16;
            bool valid=z>=0&&z<(int)depth&&y>=0&&y<(int)height;
            Word a=0,b=0,d=0;
            int begin=xoff>>4, end=(xoff+ci*n)>>4;
            unsigned row_cache=(c*4+dz)*6+dy;
            if (x0!=0) { a=last_b[row_cache]; b=last_d[row_cache]; }
            else if (valid&&wi+1>=begin&&wi+1<end) b=memory[wi+1];
            if (valid&&x0+16<width&&wi+2>=begin&&wi+2<end) d=memory[wi+2];
            last_b[row_cache]=b;last_d[row_cache]=d;
            ap_uint<512> ab=0,bd=0;
            ab.range(255,0)=a;ab.range(511,256)=b;
            bd.range(255,0)=b;bd.range(511,256)=d;
            ab >>= shift;bd >>= shift;
            unsigned slot=((c*4+dz)*6+dy)*2;
            for (unsigned j=0;j<16;j++) {
#pragma HLS UNROLL
                int x=(int)x0-1+(int)j;
                patch[j][slot]=valid&&x>=0&&x<(int)width?
                    (I16)ab.range(j*16+15,j*16):I16(0);
                if (j<2) {
                    int xx=(int)x0+15+(int)j;
                    patch[j][slot+1]=valid&&xx>=0&&xx<(int)width?
                        (I16)bd.range(j*16+15,j*16):I16(0);
                }
            }
        }
}
static void compute(Word *memory, I16 weights[16][2048], I16 patch[16][2048],
                    ap_uint<16> coords[864], unsigned tile, unsigned yoff,
                    unsigned roff, unsigned ci, unsigned co, unsigned depth,
                    unsigned height, unsigned width, float scales[32],
                    float biases[32], float rscale, float inverse_output_scale,
                    unsigned flags, unsigned &clipped) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=weights complete dim=1
#pragma HLS ARRAY_PARTITION variable=patch complete dim=1
    Acc sums[16][16];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
#pragma HLS ARRAY_PARTITION variable=sums complete dim=2
    unsigned local_clips=0;
    unsigned z0,y0,x0;origin(tile,height,width,z0,y0,x0);
    unsigned n=volume(depth,height,width);
    for (unsigned v=0;v<8;v++) {
        unsigned oz=v/4,oy=v%4;
        if (z0+oz>=depth||y0+oy>=height) continue;
        for(unsigned mb=0;mb<co;mb+=16) {
            for (unsigned i=0;i<16;i++) {
#pragma HLS UNROLL
                for (unsigned j=0;j<16;j++) {
#pragma HLS UNROLL
                    sums[i][j]=0;
                }
            }
        IntegerMAC:for (unsigned k=0;k<ci*27;k++) {
#pragma HLS PIPELINE II=1
            ap_uint<16> coord=coords[k];unsigned kx=coord&3;
            unsigned slot=(coord>>2)+oz*12+oy*2;
            I16 cached[16],wv[16];
#pragma HLS ARRAY_PARTITION variable=cached complete
#pragma HLS ARRAY_PARTITION variable=wv complete
            for (unsigned j=0;j<16;j++) {
#pragma HLS UNROLL
                cached[j]=patch[j][slot+(j<kx?1:0)];
                wv[j]=mb+j<co?weights[j][(mb>>4)*1024+k]:I16(0);
            }
            for (unsigned i=0;i<16;i++) for (unsigned j=0;j<16;j++) {
#pragma HLS UNROLL
                ap_int<32> product=wv[i]*cached[(j+kx)&15];
                sums[i][j]+=product;
            }
        }
        Word residual_rows[16];
#pragma HLS RESOURCE variable=residual_rows core=RAM_2P_LUTRAM
        for(unsigned i=0;i<16;i++){
#pragma HLS PIPELINE II=1
            unsigned m=mb+i;
            unsigned index=position(m,z0+oz,y0+oy,x0,depth,height,width);
            residual_rows[i]=(flags&16)&&m<co?memory[(roff+index)>>4]:Word(0);
        }
        Word int_line=0,float_line=0;
        Store:for (unsigned q0=0;q0<256;q0+=2) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=memory inter false
            for(unsigned lane=0;lane<2;lane++) {
#pragma HLS UNROLL
            unsigned q=q0+lane;
            unsigned m=mb+(q>>4),j=q&15;
            unsigned index=position(m,z0+oz,y0+oy,x0,depth,height,width);
            float value=(float)sums[m&15][j];
            value=value*(m<co?scales[m]:0.f);
            value=value+(m<co?biases[m]:0.f);
            if (flags&16) value=value+(float)get16(residual_rows[q>>4],j)*rscale;
            if ((flags&3)==1 && value<0) value=0;
            if ((flags&3)==2 && value<0) value=value*.01f;
            if (flags&256) {
                float_line=float_line>>32;float_line.range(255,224)=as_bits(value);
                if ((j&7)==7 && m<co) memory[(yoff+index*2+j*2-14)>>4]=float_line;
            } else {
                I16 value_q=nearest_even(value*inverse_output_scale,local_clips);
                int_line=int_line>>16;int_line.range(255,240)=(ap_uint<16>)value_q;
                if (j==15 && m<co) memory[(yoff+index)>>4]=int_line;
            }
        }
            } // two independent output pixels
        }
    }
    clipped=local_clips;
}
static void load_if(Word *memory,I16 patch[16][2048],unsigned tile,unsigned count,
                    unsigned xoff,unsigned ci,unsigned depth,unsigned height,unsigned width) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=patch complete dim=1
    if(tile<count)patch_load(memory,patch,tile,xoff,ci,depth,height,width);
}
static void compute_if(Word *memory,I16 weights[16][2048],I16 patch[16][2048],
 ap_uint<16>coords[864],unsigned tile,unsigned count,unsigned yoff,unsigned roff,
 unsigned ci,unsigned co,unsigned depth,unsigned height,unsigned width,
 float scales[32],float biases[32],float rscale,float inverse_scale,unsigned flags,unsigned &clipped) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=weights complete dim=1
#pragma HLS ARRAY_PARTITION variable=patch complete dim=1
    if(tile<count)compute(memory,weights,patch,coords,tile,yoff,roff,ci,co,depth,height,width,
                          scales,biases,rscale,inverse_scale,flags,clipped);
    else clipped=0;
}
static void step(Word *input,Word *output,I16 weights[16][2048],
 I16 current[16][2048],I16 next[16][2048],ap_uint<16>coords[864],
 unsigned tile,unsigned next_tile,unsigned count,unsigned xoff,unsigned yoff,unsigned roff,
 unsigned ci,unsigned co,unsigned depth,unsigned height,unsigned width,float scales[32],
 float biases[32],float rscale,float inverse_scale,unsigned flags,unsigned &clipped) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
#pragma HLS ARRAY_PARTITION variable=weights complete dim=1
#pragma HLS ARRAY_PARTITION variable=current complete dim=1
#pragma HLS ARRAY_PARTITION variable=next complete dim=1
    load_if(input,next,next_tile,count,xoff,ci,depth,height,width);
    compute_if(output,weights,current,coords,tile,count,yoff,roff,ci,co,depth,height,width,
               scales,biases,rscale,inverse_scale,flags,clipped);
}
unsigned mixed_conv(Word *input,Word *output,unsigned command,unsigned xoff,unsigned woff,
 unsigned yoff,unsigned poff,unsigned roff,unsigned ci,unsigned co,unsigned depth,unsigned height,
 unsigned width,float rscale,float inverse_scale,unsigned flags,unsigned &clipped) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=read_ddr depth=65536 max_read_burst_length=8 num_read_outstanding=8
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=write_ddr depth=65536 max_write_burst_length=4 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=command bundle=control
#pragma HLS INTERFACE s_axilite port=xoff bundle=control
#pragma HLS INTERFACE s_axilite port=woff bundle=control
#pragma HLS INTERFACE s_axilite port=yoff bundle=control
#pragma HLS INTERFACE s_axilite port=poff bundle=control
#pragma HLS INTERFACE s_axilite port=roff bundle=control
#pragma HLS INTERFACE s_axilite port=ci bundle=control
#pragma HLS INTERFACE s_axilite port=co bundle=control
#pragma HLS INTERFACE s_axilite port=depth bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=rscale bundle=control
#pragma HLS INTERFACE s_axilite port=inverse_scale bundle=control
#pragma HLS INTERFACE s_axilite port=flags bundle=control
#pragma HLS INTERFACE s_axilite port=clipped bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS ALLOCATION instances=step limit=1 function
    if(command==0){clipped=0;return 0x4D503136;}
    if(command!=1||!ci||ci>32||!co||co>32||!depth||depth>48||!height||height>96||
       !width||width>80||width%16||(xoff|woff|yoff|poff|roff)%16||
       (flags&~0x113U)||(flags&3)>2){clipped=0;return 0;}
    unsigned n=volume(depth,height,width);
    if ((flags&16) && roff<yoff+co*n*((flags&256)?2:1) && yoff<roff+co*n){clipped=0;return 0;}
    I16 weights[16][2048],patch0[16][2048],patch1[16][2048];
#pragma HLS ARRAY_PARTITION variable=weights complete dim=1
#pragma HLS ARRAY_PARTITION variable=patch0 complete dim=1
#pragma HLS ARRAY_PARTITION variable=patch1 complete dim=1
#pragma HLS RESOURCE variable=weights core=XPM_MEMORY uram
#pragma HLS RESOURCE variable=patch0 core=RAM_2P_BRAM
#pragma HLS RESOURCE variable=patch1 core=RAM_2P_BRAM
    float scales[32],biases[32];
    ap_uint<16>coords[864];
#pragma HLS RESOURCE variable=coords core=RAM_2P_BRAM
    for(unsigned i=0;i<co;i++) {
#pragma HLS PIPELINE II=1
        scales[i]=get32(input[(poff+i*2)>>4],i&7);
        biases[i]=get32(input[(poff+64+i*2)>>4],i&7);
    }
    for(unsigned c=0;c<ci;c++)for(unsigned z=0;z<3;z++)
        for(unsigned y=0;y<3;y++)for(unsigned x=0;x<3;x++) {
#pragma HLS PIPELINE II=1
            unsigned k=((c*3+z)*3+y)*3+x;
            coords[k]=((c*48+z*12+y*2)<<2)|x;
        }
    weights_load(input,weights,woff,ci,co);
    unsigned count=((depth+1)/2)*((height+3)/4)*(width/16);
    unsigned tile_clips=0,total_clips=0;
    step(input,output,weights,patch1,patch0,coords,count,0,count,xoff,yoff,roff,
         ci,co,depth,height,width,scales,biases,rscale,inverse_scale,flags,tile_clips);
    for(unsigned tile=0;tile<count;tile+=2) {
        step(input,output,weights,patch0,patch1,coords,tile,tile+1,count,xoff,yoff,roff,
             ci,co,depth,height,width,scales,biases,rscale,inverse_scale,flags,tile_clips);
        total_clips+=tile_clips;
        step(input,output,weights,patch1,patch0,coords,tile+1,tile+2,count,xoff,yoff,roff,
             ci,co,depth,height,width,scales,biases,rscale,inverse_scale,flags,tile_clips);
        total_clips+=tile_clips;
    }
    clipped=total_clips;
    return 1;
}
