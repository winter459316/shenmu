// FP32 4x4x4 stride-2/pad-1 transposed convolution. 64 parallel multiplies.
// DDR format: X[Ci,D,H,W], packed weights[8,Co,Ci*8], Y[8,Co,D*H*W].
#include <stdint.h>
#include <ap_int.h>
static float unpack(ap_uint<32> b){union{unsigned u;float f;}x;x.u=b;return x.f;}
static ap_uint<32> pack(float f){union{unsigned u;float f;}x;x.f=f;return x.u;}
static float lane(ap_uint<512> word,unsigned pos){
#pragma HLS INLINE
 switch(pos){
 case 0:return unpack(word.range(31,0));
 case 1:return unpack(word.range(63,32));
 case 2:return unpack(word.range(95,64));
 case 3:return unpack(word.range(127,96));
 case 4:return unpack(word.range(159,128));
 case 5:return unpack(word.range(191,160));
 case 6:return unpack(word.range(223,192));
 case 7:return unpack(word.range(255,224));
 case 8:return unpack(word.range(287,256));
 case 9:return unpack(word.range(319,288));
 case 10:return unpack(word.range(351,320));
 case 11:return unpack(word.range(383,352));
 case 12:return unpack(word.range(415,384));
 case 13:return unpack(word.range(447,416));
 case 14:return unpack(word.range(479,448));
 case 15:return unpack(word.range(511,480));
 default:return 0.f;
 }
}
unsigned fast_deconv(ap_uint<512> *memory,unsigned command,unsigned xoff,unsigned woff,
 unsigned yoff,unsigned ci,unsigned co,unsigned depth,unsigned height,unsigned width){
#pragma HLS INTERFACE m_axi port=memory offset=slave bundle=ddr depth=1024 max_read_burst_length=64 max_write_burst_length=64 num_read_outstanding=4 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=memory bundle=control
#pragma HLS INTERFACE s_axilite port=command bundle=control
#pragma HLS INTERFACE s_axilite port=xoff bundle=control
#pragma HLS INTERFACE s_axilite port=woff bundle=control
#pragma HLS INTERFACE s_axilite port=yoff bundle=control
#pragma HLS INTERFACE s_axilite port=ci bundle=control
#pragma HLS INTERFACE s_axilite port=co bundle=control
#pragma HLS INTERFACE s_axilite port=depth bundle=control
#pragma HLS INTERFACE s_axilite port=height bundle=control
#pragma HLS INTERFACE s_axilite port=width bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
 if(command==0)return 0x46445031;
 if(command!=1||ci==0||ci>112||co==0||co>56||depth==0||depth>24||height==0||height>48||width==0||width>40)return 0;
 const unsigned n=depth*height*width,kmax=ci*8;
 if(ci%2 || n%16 || xoff%16 || woff%16 || yoff%16)return 0;
 // Co partition across eight URAM banks, one weight from each bank per cycle.
 ap_uint<64> weights[8][4096];
#pragma HLS ARRAY_PARTITION variable=weights complete dim=1
#pragma HLS RESOURCE variable=weights core=XPM_MEMORY uram
 float input[8][2048];
#pragma HLS ARRAY_PARTITION variable=input complete dim=1
#pragma HLS RESOURCE variable=input core=RAM_2P_BRAM
 float acc[8][8][8];
#pragma HLS ARRAY_PARTITION variable=acc complete dim=1
#pragma HLS ARRAY_PARTITION variable=acc complete dim=2
#pragma HLS RESOURCE variable=acc core=RAM_2P_LUTRAM
 unsigned zs[16],ys[16],xs[16];
 for(unsigned phase=0;phase<8;phase++){
  LoadWeights:for(unsigned m=0;m<co;m++)for(unsigned k=0;k<kmax;k+=16){
   ap_uint<512> line=memory[(woff+(phase*co+m)*kmax+k)>>4];
   // Actual model Ci values are even, so each channel row is 16-word aligned.
   for(unsigned j=0;j<8;j++){
#pragma HLS PIPELINE II=1
    if(k+j*2<kmax)weights[m&7][(m>>3)*512+((k+j*2)>>1)]=line.range(63,0);
    line=line>>64;
   }
  }
  unsigned zz=0,yy=0,xx=0;
  for(unsigned nb=0;nb<n;nb+=16){
   Coords:for(unsigned j=0;j<16;j++){
#pragma HLS PIPELINE II=1
    zs[j]=zz;ys[j]=yy;xs[j]=xx;
    xx++;if(xx==width){xx=0;yy++;if(yy==height){yy=0;zz++;}}
   }
   LoadInput:for(unsigned k=0;k<kmax;k++){
    int dz=(int)((phase>>2)&1)-(int)((k>>2)&1);
    int dy=(int)((phase>>1)&1)-(int)((k>>1)&1);
    int dx=(int)(phase&1)-(int)(k&1);
    int base=(int)xoff+(int)((k>>3)*n+nb)+dz*(int)(height*width)+dy*(int)width+dx;
    int word=base>>4;unsigned shift=base&15;
    ap_uint<512> line[2];
#pragma HLS ARRAY_PARTITION variable=line complete
    // Two aligned 512-bit words contain every candidate for this 16-voxel tile.
    // Never issue an address below the reserved arena, including padded borders.
    if(word>=0){
     for(unsigned q=0;q<2;q++){
#pragma HLS PIPELINE II=1
      line[q]=memory[word+q];
     }
    }else{line[0]=0;line[1]=word==-1?memory[0]:ap_uint<512>(0);}
    for(unsigned j=0;j<16;j++){
#pragma HLS PIPELINE II=1
     int z=(int)zs[j]+dz,y=(int)ys[j]+dy,x=(int)xs[j]+dx;
     bool ok=nb+j<n&&z>=0&&z<(int)depth&&y>=0&&y<(int)height&&x>=0&&x<(int)width;
     unsigned offset=shift+j;
     ap_uint<512> selected=offset<16?line[0]:line[1];unsigned bit=(offset&15)*32;
     input[j&7][k*2+(j>>3)]=ok?lane(selected,offset&15):0.f;
    }
   }
   for(unsigned mb=0;mb<co;mb+=16){
    Clear:for(unsigned a=0;a<8;a++){
#pragma HLS PIPELINE II=1
     for(unsigned i=0;i<8;i++)for(unsigned j=0;j<8;j++){
#pragma HLS UNROLL
      acc[i][j][a]=0;
     }
    }
    // Each accumulator is revisited after eight cycles (four quadrants x two partial sums).
    Mac:for(unsigned t=0;t<kmax*4;t++){
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=acc inter false
#pragma HLS EXPRESSION_BALANCE off
     unsigned k=t>>2,mi=((t>>1)&1)*8,nj=(t&1)*8,p=k&1;
     float av[8],bv[8];
#pragma HLS ARRAY_PARTITION variable=av complete
#pragma HLS ARRAY_PARTITION variable=bv complete
     for(unsigned i=0;i<8;i++){
#pragma HLS UNROLL
      ap_uint<64> word=weights[i][((mb+mi)>>3)*512+(k>>1)];
      av[i]=mb+mi+i<co?unpack(k&1?word.range(63,32):word.range(31,0)):0.f;
      bv[i]=input[i][k*2+(nj>>3)];
     }
     for(unsigned i=0;i<8;i++)for(unsigned j=0;j<8;j++){
#pragma HLS UNROLL
      float product=av[i]*bv[j];
      unsigned slot=(t&3)*2+p;
      acc[i][j][slot]=acc[i][j][slot]+product;
     }
    }
    Store:for(unsigned i=0;i<16;i++){
     ap_uint<512> line=0;
     for(unsigned j=0;j<16;j++){
#pragma HLS PIPELINE II=1
      unsigned slot=((i>>3)*2+(j>>3))*2;
      line=line>>32;
      line.range(511,480)=pack(acc[i&7][j&7][slot]+acc[i&7][j&7][slot+1]);
     }
     if(mb+i<co)memory[(yoff+(phase*co+mb+i)*n+nb)>>4]=line;
    }
   }
  }
 }
 return 1;
}
