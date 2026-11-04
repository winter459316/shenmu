// Bounded, orientation-aware multiscale dark-ridge enhancement. Display only.
static unsigned vessel_signal(rgb p){
#pragma HLS INLINE
    return (3*(unsigned)p.range(15,8)+(unsigned)p.range(7,0)+2)>>2;
}
static unsigned min2(unsigned a,unsigned b){return a<b?a:b;}
static unsigned max2(unsigned a,unsigned b){return a>b?a:b;}
static rgb vessel_pixel(rgb window[9][9]){
#pragma HLS INLINE
    unsigned s[9][9];
#pragma HLS ARRAY_PARTITION variable=s complete dim=0
    for(int y=0;y<9;y++)for(int x=0;x<9;x++){
#pragma HLS UNROLL
        s[y][x]=vessel_signal(window[y][x]);
    }
    const int dy[4]={0,1,1,1},dx[4]={1,0,1,-1};
    const int radii[3]={1,2,4};unsigned center=s[4][4],response=0;
    for(int d=0;d<4;d++){
#pragma HLS UNROLL
        unsigned along=(s[4+dx[d]][4-dy[d]]+s[4-dx[d]][4+dy[d]]+1)>>1;
        unsigned supported=max2(center,along);
        for(int r=0;r<3;r++){
#pragma HLS UNROLL
            int yy=radii[r]*dy[d],xx=radii[r]*dx[d];
            unsigned flank=min2(s[4+yy][4+xx],s[4-yy][4-xx]);
            unsigned v=flank>supported+3?flank-supported-3:0;
            response=max2(response,v);
        }
    }
    response=min2(response,24);
    unsigned dark=center<=12?0:min2((center-12)*4,64);
    unsigned light=center>=244?0:min2((244-center)*4,64);
    unsigned delta=((((response*9+2)>>2)*min2(dark,light))+32)>>6;
    rgb p=window[4][4];
    if((unsigned)p.range(7,0)>220 && (unsigned)p.range(15,8)>220 && (unsigned)p.range(23,16)>220)delta=0;
    rgb out=0;
    for(int c=0;c<3;c++){
#pragma HLS UNROLL
        unsigned value=p.range(8*c+7,8*c);
        out.range(8*c+7,8*c)=value>delta?value-delta:0;
    }
    return out;
}
static void read_eye(word*input,hls::stream<word>&s,unsigned eye,unsigned w,unsigned h){
#pragma HLS INLINE off
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w/8;x++){
#pragma HLS PIPELINE II=1
        s.write(input[y*w/4+eye*w/8+x]);
    }
}
static void write_eye(hls::stream<word>&s,word*output,unsigned eye,unsigned w,unsigned h){
#pragma HLS INLINE off
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w/8;x++){
#pragma HLS PIPELINE II=1
        output[y*w/4+eye*w/8+x]=s.read();
    }
}
static void vessel_window(hls::stream<word>&input,hls::stream<word>&output,unsigned w,unsigned h){
#pragma HLS INLINE off
    rgb rows[8][644];rgb win[9][9];
#pragma HLS ARRAY_PARTITION variable=rows complete dim=1
#pragma HLS RESOURCE variable=rows core=RAM_S2P_BRAM
#pragma HLS DEPENDENCE variable=rows inter false
#pragma HLS ARRAY_PARTITION variable=win complete dim=0
    word in=0,out=0;
    for(unsigned y=0;y<h+4;y++)for(unsigned x=0;x<w+4;x++){
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_FLATTEN
        rgb pixel=0;
        if(y<h && x<w){
            if(x%4==0)in=input.read();
            pixel=in.range((x%4)*32+23,(x%4)*32);
        }
        rgb column[9];
#pragma HLS ARRAY_PARTITION variable=column complete
        for(int r=0;r<8;r++){
#pragma HLS UNROLL
            // Guard uninitialized rows on the first eight scanlines.
            column[r]=y>=(unsigned)(8-r)?rows[r][x]:(rgb)0;
        }
        column[8]=pixel;
        for(int r=0;r<8;r++){
#pragma HLS UNROLL
            rows[r][x]=column[r+1];
        }
        for(int r=0;r<9;r++){
#pragma HLS UNROLL
            for(int c=0;c<8;c++){
#pragma HLS UNROLL
                win[r][c]=x==0?(rgb)0:win[r][c+1];
            }
            win[r][8]=column[r];
        }
        if(y>=4 && x>=4){
            unsigned oy=y-4,ox=x-4;rgb q=win[4][4];
            if(oy>=4 && oy<h-4 && ox>=4 && ox<w-4)q=vessel_pixel(win);
            ap_uint<32> p=0;p.range(23,0)=q;
            out.range((ox%4)*32+31,(ox%4)*32)=p;
            if(ox%4==3)output.write(out);
        }
    }
}
static void vessel_eye(word*input,word*output,unsigned eye,unsigned w,unsigned h){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<word> a,b;
#pragma HLS STREAM variable=a depth=256
#pragma HLS STREAM variable=b depth=256
    read_eye(input,a,eye,w,h);vessel_window(a,b,w/2,h);write_eye(b,output,eye,w,h);
}
static void vessels(word*input,word*output,unsigned w,unsigned h){
#pragma HLS INLINE off
    for(unsigned eye=0;eye<2;eye++)vessel_eye(input,output,eye,w,h);
}
