from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parents[1]/'hls/completion_cg'
for n in ('completion_cg.cpp','completion_cg.h','test_completion_cg.cpp'):
    s=(SOURCE/n).read_text().replace('W=640','W=320').replace('contain 640 pixels','contain 320 pixels')
    if n=='completion_cg.cpp':s=s.replace('if(command==0)return 0x43475032U;','if(command==0)return 0x43475032U;\n if(command==4)return W;')
    if n=='test_completion_cg.cpp':
        s=s.replace('completion_cg(memory,4,H','completion_cg(memory,5,H')
        s=s.replace('puts("PL_COMPLETION_CG_EXACT_PASS', 'if(completion_cg(memory,4,H,STRIDE,0)!=320)return 5;\n puts("PL_COMPLETION_CG_EXACT_PASS')
    (ROOT/n).write_text(s)
