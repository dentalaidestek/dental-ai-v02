#!/usr/bin/env python3
"""Ana sayfa Foto Fikir kartı görseli: 642x179 webp, lacivert tema, özgün grafik."""
from pathlib import Path
from PIL import Image, ImageDraw

TARGET = Path("app/static/dashboard/dental_ai_foto_fikir_card.webp")
W, H = 642, 179
NAVY_DEEP=(7,22,43); NAVY=(11,35,65); NAVY_MID=(24,53,91); BLUE_SOFT=(66,98,140)
ICE=(218,228,240); WHITE=(255,255,255); AMBER=(233,168,76)

def rounded(draw, box, radius, fill, outline=None):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline)

def mini_slide(draw, x, y, w, h, *, accent):
    rounded(draw,(x,y,x+w,y+h),10,WHITE)
    rounded(draw,(x+10,y+10,x+10+int(w*0.52),y+22),5,accent)
    line_y=y+34
    for frac in (0.86,0.74,0.58):
        draw.line((x+10,line_y,x+10+int((w-20)*frac),line_y),fill=ICE,width=3)
        line_y+=9

def tooth(draw,x,y,s):
    pts=[(x+0.18*s,y+0.06*s),(x+0.34*s,y+0.10*s),(x+0.50*s,y+0.02*s),(x+0.66*s,y+0.10*s),
         (x+0.82*s,y+0.06*s),(x+0.94*s,y+0.28*s),(x+0.88*s,y+0.50*s),(x+0.80*s,y+0.70*s),
         (x+0.72*s,y+0.94*s),(x+0.62*s,y+0.94*s),(x+0.58*s,y+0.60*s),(x+0.50*s,y+0.60*s),
         (x+0.46*s,y+0.94*s),(x+0.36*s,y+0.94*s),(x+0.26*s,y+0.62*s),(x+0.14*s,y+0.36*s),(x+0.06*s,y+0.24*s)]
    draw.polygon(pts,fill=WHITE)

def build():
    image=Image.new("RGB",(W,H),NAVY_DEEP); draw=ImageDraw.Draw(image)
    for x in range(W):
        t=x/W
        draw.line((x,0,x,H),fill=(int(NAVY_DEEP[0]+(NAVY_MID[0]-NAVY_DEEP[0])*t),
            int(NAVY_DEEP[1]+(NAVY_MID[1]-NAVY_DEEP[1])*t),int(NAVY_DEEP[2]+(NAVY_MID[2]-NAVY_DEEP[2])*t)))
    overlay=Image.new("RGBA",(W,H),(0,0,0,0)); odraw=ImageDraw.Draw(overlay)
    odraw.polygon([(W*0.55,0),(W,0),(W,H),(W*0.75,H)],fill=(255,255,255,10))
    image=Image.alpha_composite(image.convert("RGBA"),overlay).convert("RGB")
    draw=ImageDraw.Draw(image)
    mini_slide(draw,36,26,200,62,accent=(66,98,140))
    mini_slide(draw,58,96,200,62,accent=AMBER)
    tooth(draw,470,34,96)
    rounded(draw,(434,118,566,132),7,BLUE_SOFT)
    rounded(draw,(444,122,470,128),3,WHITE)
    for i,frac in enumerate((0.9,0.72,0.5)):
        draw.line((int(W*frac),146+i*8,W-20,146+i*8),fill=ICE,width=2)
    return image

def main():
    image=build()
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    image.save(TARGET,"WEBP",quality=88)
    with Image.open(TARGET) as check:
        gray=check.convert("L"); hist=gray.histogram()
        nonwhite=1-hist[255]/max(1,sum(hist))
    assert check.size==(W,H), check.size
    assert nonwhite>0.5, f"boş görsel? non-white={nonwhite:.2f}"
    print(f"OK {TARGET} {check.size} non-white={nonwhite:.2f} bytes={TARGET.stat().st_size}")

if __name__=="__main__":
    main()
