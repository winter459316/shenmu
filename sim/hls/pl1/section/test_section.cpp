#include <vector>
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
extern "C" unsigned section_accel(const float*,const float*,uint32_t*,unsigned,unsigned);
int main(){
 float v[8][3]={{-1,-1,-1},{1,-1,-1},{1,1,-1},{-1,1,-1},{-1,-1,1},{1,-1,1},{1,1,1},{-1,1,1}};
 int f[12][3]={{0,2,1},{0,3,2},{4,5,6},{4,6,7},{0,1,5},{0,5,4},{1,2,6},{1,6,5},{2,3,7},{2,7,6},{3,0,4},{3,4,7}};
 std::vector<float> t;for(int i=0;i<12;i++)for(int j=0;j<3;j++)for(int k=0;k<3;k++)t.push_back(v[f[i][j]][k]);
 t.resize(4500000); // Co-simulation copies the declared AXI depth, not just count.
 std::vector<uint32_t> out(262160);float p[16]={0,0,1,0,1,0,0,0,1,0,-2,-2,128,0,0,0};
 assert(section_accel(t.data(),p,out.data(),12,0)==0x53454331);
 assert(section_accel(t.data(),p,out.data(),12,2)==0);
 assert(out[2]==8);union Bits{float f;uint32_t u;}b;
 b.u=out[6];assert(b.f==128);b.u=out[7];assert(b.f==128);b.u=out[8];assert(b.f==384);b.u=out[9];assert(b.f==384);
 for(int c=0;c<3;c++){
   p[3]=c==0?0:c==1?-0.999f:-2;
   assert(section_accel(t.data(),p,out.data(),12,1)==0);assert(out[4]==0);
   for(int y=0;y<512;y++)for(int x=0;x<512;x++)assert(out[16+y*512+x]==(c<2&&x>=128&&x<384&&y>=128&&y<384?255:0));
 }
 puts("SECTION_CUBE_ALL_PIXELS_PASS");return 0;
}
