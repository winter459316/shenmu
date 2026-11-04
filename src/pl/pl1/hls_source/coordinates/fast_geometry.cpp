#include <ap_int.h>
#include <stdint.h>
typedef ap_uint<128> Word;
static double f64(uint64_t u){union{uint64_t u;double d;}v;v.u=u;return v.d;}
static float f32(uint32_t u){union{uint32_t u;float f;}v;v.u=u;return v.f;}
static uint32_t bits(float f){union{uint32_t u;float f;}v;v.f=f;return v.u;}
static uint64_t bits64(double d){union{uint64_t u;double d;}v;v.d=d;return v.u;}
static bool zero64(uint64_t b){return (b&0x7fffffffffffffffULL)==0;}
static bool finite32(uint32_t b){return (b&0x7f800000U)!=0x7f800000U;}
static bool finite64(uint64_t b){return (b&0x7ff0000000000000ULL)!=0x7ff0000000000000ULL;}
static bool positive32(uint32_t b){return (b&0x80000000U)==0&&(b&0x7fffffffU)!=0&&finite32(b);}

// Canonical rectified Q, including non-square pixel scaling and principal-point offset.
// FP32 disparity bits are never quantized; all projection arithmetic is FP64.
unsigned fast_geometry(Word* arena,unsigned command,unsigned width,unsigned height,
                       unsigned input_offset,unsigned output_offset,unsigned& valid_count){
#pragma HLS INTERFACE m_axi port=arena offset=slave bundle=ddr depth=4096 max_read_burst_length=64 max_write_burst_length=64
#pragma HLS INTERFACE s_axilite port=arena bundle=control
#pragma HLS INTERFACE s_axilite port=command bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=input_offset bundle=control
#pragma HLS INTERFACE s_axilite port=output_offset bundle=control
#pragma HLS INTERFACE s_axilite port=valid_count bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS ALLOCATION instances=ddiv limit=1 operation
#pragma HLS ALLOCATION instances=dmul limit=1 operation
#pragma HLS ALLOCATION instances=dadd limit=1 operation
 if(command==0){valid_count=0;return 0x46475031U;}
 if(command!=1||!width||width>320||!height||height>360||(width&1)||input_offset<16||input_offset>300000||output_offset>300000||
    output_offset<input_offset+(width*height)/2||output_offset+width*height>300000){valid_count=0;return 0;}
 double q[16];
#pragma HLS ARRAY_PARTITION variable=q complete
 for(unsigned i=0;i<8;i++){
#pragma HLS UNROLL
  Word w=arena[i];uint64_t a=w.range(63,0),b=w.range(127,64);
  if(!finite64(a)||!finite64(b)){valid_count=0;return 0;}
  q[2*i]=f64(a);q[2*i+1]=f64(b);
 }
 for(unsigned i=0;i<16;i++){
#pragma HLS UNROLL
  if(i!=0&&i!=3&&i!=5&&i!=7&&i!=11&&i!=14&&i!=15&&!zero64(bits64(q[i]))){valid_count=0;return 0;}
 }
 if((bits64(q[11])>>63)||zero64(bits64(q[11]))||zero64(bits64(q[14]))){valid_count=0;return 0;}
 double nx[320];
#pragma HLS RESOURCE variable=nx core=RAM_1P_BRAM
 Word inrow[160],outrow[320];
#pragma HLS RESOURCE variable=inrow core=RAM_1P_BRAM
#pragma HLS RESOURCE variable=outrow core=RAM_1P_BRAM
 Columns:for(unsigned x=0;x<width;x++){
#pragma HLS PIPELINE
  double mx=q[0]*(double)x;nx[x]=mx+q[3];
 }
 unsigned count=0;
 Rows:for(unsigned y=0;y<height;y++){
#pragma HLS LOOP_TRIPCOUNT min=1 max=360
  double my=q[5]*(double)y;double ny=my+q[7];
  Load:for(unsigned t=0;t<width/2;t++){
#pragma HLS PIPELINE II=1
   inrow[t]=arena[input_offset+y*(width/2)+t];
  }
  Points:for(unsigned x=0;x<width;x++){
#pragma HLS PIPELINE II=3
   Word w=inrow[x>>1];ap_uint<64> rec=(x&1)?w.range(127,64):w.range(63,0);
   uint32_t db=rec.range(31,0);float d=f32(db);
   bool initial=rec[32]&&positive32(db);
   double md=q[14]*(double)(initial?d:1.0f);double den=md+q[15];
   bool nonzero=!zero64(bits64(den));double denominator=nonzero?den:1.0;
   double numerator[3]={nx[x],ny,q[11]};
#pragma HLS ARRAY_PARTITION variable=numerator complete
   uint32_t v[3];
#pragma HLS ARRAY_PARTITION variable=v complete
   Divide:for(unsigned axis=0;axis<3;axis++){
    double quotient=numerator[axis]/denominator;v[axis]=bits((float)quotient);
   }
   bool valid=initial&&nonzero&&finite32(v[0])&&finite32(v[1])&&positive32(v[2]);
   Word out=0;
   for(unsigned axis=0;axis<3;axis++){
#pragma HLS UNROLL
    out.range(axis*32+31,axis*32)=valid?v[axis]:0x7fc00000U;
   }
   out.range(127,96)=valid?1:0;outrow[x]=out;
   if(valid)count++;
  }
  Store:for(unsigned x=0;x<width;x++){
#pragma HLS PIPELINE II=1
   arena[output_offset+y*width+x]=outrow[x];
  }
 }
 valid_count=count;return 1;
}
