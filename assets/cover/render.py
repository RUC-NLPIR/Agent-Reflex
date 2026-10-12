#!/usr/bin/env python3
"""Render the paper-style mascot, ASCII title and reflective interaction as a GIF.
Requires Python 3.10+, Pillow and ffmpeg. No network is needed to render.
"""
from __future__ import annotations
import argparse
from functools import lru_cache
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ROOT=Path(__file__).resolve().parents[2]
W,H,S=1280,700,2
FPS,SCENE=24,10
BG='#F5F8FD'; NAVY='#183560'; BLUE='#356CB1'; CYAN='#8DE7EE'
TEAL='#31858A'; PURPLE='#7153AC'; RED='#E99B94'; MUTED='#6D809D'
LINE='#CDDAEC'; TERMINAL='#142D50'; WHITE='#F5FAFF'
GLYPHS={
 'A':['01110','11011','11011','11111','11011','11011','11011'],
 'G':['01111','11000','11000','11011','11011','11011','01111'],
 'E':['11111','11000','11000','11110','11000','11000','11111'],
 'N':['11001','11101','11101','11011','11011','11001','11001'],
 'T':['11111','00110','00110','00110','00110','00110','00110'],
 '-':['00000','00000','00000','11111','00000','00000','00000'],
 'R':['11110','11011','11011','11110','11100','11010','11011'],
 'F':['11111','11000','11000','11110','11000','11000','11000'],
 'L':['11000','11000','11000','11000','11000','11000','11111'],
 'X':['11011','11011','01110','00100','01110','11011','11011'],
}
CASES=[
 {'tag':'TOOL FEEDBACK','source':'environment / MCP tool','request':"get_record(id='R42')",
  'event':['503','Service unavailable'], 'plan':['Transient failure.','Back off. Retry. Verify.'],
  'action':'bounded retry','result':['200 OK','Result verified'], 'log':'record.id == R42'},
 {'tag':'USER CORRECTION','source':'interaction / user','request':'user > Pause.',
  'event':['Check the ID','before updating.'], 'plan':['Resolve the target.','Revise. Read back. Verify.'],
  'action':'recheck and revise','result':['Exact match','Update verified'], 'log':'read_back == intended'},
]

def color(c):return tuple(int(c[i:i+2],16) for i in (1,3,5)) if isinstance(c,str) else c

def mix(a,b,p):
 p=max(0,min(1,p));return tuple(round(x+(y-x)*p) for x,y in zip(color(a),color(b)))

def ease(p):p=max(0,min(1,p));return p*p*(3-2*p)

def rise(t,start,d=.35):return ease((t-start)/d)

@lru_cache(maxsize=80)
def font(size,weight='regular',mono=False):
 if mono:
  for p in ['/System/Library/Fonts/Menlo.ttc','/System/Library/Fonts/SFNSMono.ttf']:
   if Path(p).exists():return ImageFont.truetype(p,round(size*S))
  return ImageFont.truetype('DejaVuSansMono.ttf',round(size*S))
 if FONT_OVERRIDE:return ImageFont.truetype(FONT_OVERRIDE,round(size*S))
 p='/System/Library/Fonts/Avenir Next.ttc'
 if Path(p).exists():return ImageFont.truetype(p,round(size*S),index={'regular':7,'medium':5,'demi':2,'bold':0}[weight])
 return ImageFont.truetype('DejaVuSans-Bold.ttf' if weight in ['demi','bold'] else 'DejaVuSans.ttf',round(size*S))

class Canvas:
 def __init__(self):
  self.im=Image.new('RGB',(W*S,H*S),BG);self.d=ImageDraw.Draw(self.im)
 def rect(self,b,fill,r=0,outline=None,width=1):
  b=tuple(round(v*S) for v in b)
  if r:self.d.rounded_rectangle(b,round(r*S),fill,outline,round(width*S))
  else:self.d.rectangle(b,fill,outline,round(width*S))
 def line(self,pts,fill=LINE,width=1):self.d.line([(round(x*S),round(y*S)) for x,y in pts],fill,width=round(width*S),joint='curve')
 def circle(self,x,y,r,fill,outline=None,width=1):self.d.ellipse(tuple(round(v*S) for v in [x-r,y-r,x+r,y+r]),fill,outline,round(width*S))
 def text(self,x,y,s,size=18,fill=NAVY,weight='regular',anchor='la',mono=False):
  self.d.text((round(x*S),round(y*S)),s,font=font(size,weight,mono),fill=fill,anchor=anchor)
 def image(self):return self.im.resize((W,H),Image.Resampling.LANCZOS)

@lru_cache(maxsize=1)
def title_assets():
 mask=Image.new('L',(W*S,H*S));d=ImageDraw.Draw(mask)
 cells=[];cell=14;x0=(W-71*cell)/2;y0=47
 for i,ch in enumerate('AGENT-REFLEX'):
  for row,s in enumerate(GLYPHS[ch]):
   for col,v in enumerate(s):
    if v=='1':
     x=x0+(i*6+col)*cell;y=y0+row*cell
     d.rectangle((round(x*S),round(y*S),round((x+cell)*S),round((y+cell)*S)),fill=255)
     cells.append((x,y,row))
 edge=ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(5)),mask)
 layer=Image.new('RGBA',(W*S,H*S))
 for off in [10,6,3]:
  shadow=Image.new('RGBA',layer.size,(*color('#8BA7CE'),255))
  shifted=Image.new('L',mask.size);shifted.paste(edge,(off*S,off*S))
  layer.paste(shadow,(0,0),shifted)
 gradient=Image.new('RGB',(W*S,H*S));gd=ImageDraw.Draw(gradient)
 for y in range(45*S,146*S):gd.line([(0,y),(W*S,y)],fill=mix('#5188CB','#163A73',(y/S-45)/101))
 layer.paste(gradient,(0,0),mask)
 return layer,cells

@lru_cache(maxsize=6)
def sprite(i):
 sheet=Image.open(ROOT/'assets/cover/robot-poses.png').convert('RGBA')
 cw,ch=sheet.width//3,sheet.height//2
 return sheet.crop(((i%3)*cw,(i//3)*ch,(i%3+1)*cw,(i//3+1)*ch)).resize((294*S,294*S),Image.Resampling.LANCZOS)

def arrow(c,a,b,y,progress=0,col=BLUE):
 c.line([(a,y),(b,y)],LINE,1.4);c.line([(b-6,y-5),(b,y),(b-6,y+5)],LINE,1.4)
 if progress>0:
  xx=a+(b-a)*min(progress,1);c.line([(a,y),(xx,y)],col,1.8)
  c.circle(xx,y,3,col)

def base(c,seconds):
 # Very sparse technical marks, with generous clear space.
 for x,y in [(48,45),(1232,45),(48,570),(1232,570)]:
  c.line([(x-5,y),(x+5,y)],LINE);c.line([(x,y-5),(x,y+5)],LINE)
 c.text(48,18,'>_ AGENT-REFLEX',11,MUTED,mono=True)
 c.text(1232,18,'RUC-NLPIR / REFLECTION LEARNING',11,MUTED,anchor='ra',mono=True)
 layer,cells=title_assets();c.im.paste(layer,(0,0),layer)
 # A restrained scan glints across the block/ASCII lettering once per scene.
 sweep=150+(seconds%SCENE)/SCENE*1040
 for x,y,row in cells:
  p=max(0,1-abs(x-sweep)/35)*.28
  if p:c.rect((x+1,y+1,x+13,y+13),mix(mix('#5188CB','#163A73',row/7),CYAN,p))
 c.text(640,175,'Teaching Language Agents to Act Reflectively',23,NAVY,'medium',anchor='ma')
 c.line([(48,588),(1232,588)],LINE)
 c.text(48,604,'LEARNED IN TRAINING',11,MUTED,mono=True)
 c.text(1232,604,'SKILL-FREE AT INFERENCE',11,MUTED,anchor='ra',mono=True)
 for x,num,title,detail,col in [
  (48,'01','RSD','Discover recovery skills',BLUE),
  (458,'02','ReSFT','Learn verified reflection',PURPLE),
  (867,'03','ORPO','Noisy RL + skill-guided OPD',TEAL)]:
  c.text(x,638,num,13,col,mono=True);c.text(x+35,629,title,25,NAVY,'bold')
  c.text(x+35,668,detail,16,MUTED,'medium')
 for x in [374,784]:arrow(c,x,x+48,654,1,'#8B9DB8')

def terminal(c,box,heading,col=BLUE):
 x,y,w,h=box;c.rect((x,y,x+w,y+h),TERMINAL,5,'#2A4871')
 c.line([(x,y+36),(x+w,y+36)],'#335174')
 for i in range(3):c.circle(x+16+i*11,y+18,2.7,['#668DBD','#8474AD','#70B9B7'][i])
 c.text(x+60,y+7,heading,12,'#ADC4E4',mono=True)
 c.rect((x,y+h-2,x+w,y+h),col)

def phase_pose(t):
 stages=[(0,0),(1.05,1),(2.3,2),(4.45,3),(5.55,4),(6.75,5)]
 current=0;old=0;start=0
 for threshold,pose in stages:
  if t>=threshold:old=current;current=pose;start=threshold
 return current,old,rise(t,start,.22)

def mascot(c,t):
 pose,old,p=phase_pose(t)
 image=sprite(pose)
 if old!=pose and p<1:image=Image.blend(sprite(old),image,p)
 bob=1.8*math.sin(t*2.4)
 if pose==1 and t<1.6:bob+=3*math.sin(t*45)
 if pose==2:image=image.rotate(1.6*math.sin(t*2.2),Image.Resampling.BICUBIC)
 if pose==3:bob+=1.2*math.sin(t*24)
 if pose==5:bob-=5*math.sin(min(1,(t-6.75)/.7)*math.pi)
 # The pose sheet is preserved; only its placement moves in the animation.
 c.im.paste(image,(round((640-147)*S),round((215+bob)*S)),image)
 # Minimal orbiting ASCII cues communicate thinking instead of extra UI panels.
 if pose==2:
  for i,char in enumerate(['?','+','·']):
   a=t*1.25+i*2.1
   c.text(640+135*math.cos(a),341+89*math.sin(a),char,16,BLUE,anchor='mm',mono=True)
 if pose==5:
  for i in range(6):
   a=i*math.pi/3;radius=122+9*math.sin((t-6.75)*3+i)
   x,y=640+radius*math.cos(a),348+radius*.67*math.sin(a)
   c.text(x,y,'+' if i%2 else '*',14,TEAL,anchor='mm',mono=True)

def scene(c,case_id,t):
 case=CASES[case_id];done=t>=6.75;reflection=t>=2.3
 for i,(x,w) in enumerate([(437,186),(643,202)]):
  c.text(x,219,'['+CASES[i]['tag']+']',12,BLUE if i==case_id else '#9BAAC0',mono=True)
 c.text(1232,219,'ILLUSTRATIVE INTERACTION',10,MUTED,anchor='ra',mono=True)
 left=(48,278,348,177);right=(884,278,348,177)
 terminal(c,left,case['source']);terminal(c,right,'outcome / '+('verified' if done else 'pending'),TEAL if done else BLUE)
 c.text(68,329,case['request'],17,'#A5D3FF',mono=True)
 if t<1.05:
  c.text(68,365,'request sent'+'.'*int(t*3%4),21,WHITE,'demi')
  c.text(68,408,'awaiting feedback_',14,'#93AACB',mono=True)
 else:
  c.text(68,361,case['event'][0],27 if case_id==0 else 22,RED if case_id==0 else '#CED6FF','bold')
  c.text(68,406,case['event'][1],20,WHITE,'medium')
 if done:
  c.text(904,329,case['result'][0],28,CYAN,'bold')
  c.text(904,374,case['result'][1],21,WHITE,'demi')
  c.text(904,414,'✓ '+case['log'],13,'#A3CBCB',mono=True)
 else:
  c.text(904,334,'waiting for recovery',18,'#B2C4DF',mono=True)
  if t>=4.45:
   txt=case['action'];typed=txt[:max(1,int((t-4.45)*20))]
   c.text(904,378,'> '+typed+('_' if int(t*3)%2 else ''),16,'#9AD9DE',mono=True)
  else:c.text(904,382,'no result assumed_',15,'#738EAF',mono=True)
 arrow(c,408,482,352,rise(t,.2,.7) if t<1.05 else 1,BLUE)
 arrow(c,798,872,352,rise(t,4.45,.7),TEAL)
 if .2<t<1.05:c.text(424,321,'{}',13,BLUE,mono=True)
 if 4.45<t<5.55:c.text(821,321,'{}',13,TEAL,mono=True)
 mascot(c,t)
 # A typed reflection line sits under the mascot, not over its face.
 c.rect((443,501,837,562),'#EAF1FC',4,'#CFDCEF')
 c.text(463,509,'02 REFLECT >' if reflection else '02 REFLECT / awaiting evidence',11,PURPLE if reflection else MUTED,mono=True)
 if reflection:
  txt=case['plan'][1] if t>=4.45 else case['plan'][0]
  elapsed=t-(4.45 if t>=4.45 else 2.3)
  txt=txt[:max(1,int(elapsed*27))]
  c.text(463,531,txt+('_' if int(t*3)%2 and not done else ''),17,NAVY,mono=True)
 else:c.text(463,531,'Read the evidence.',17,NAVY,mono=True)
 # The phases complete in order and every loop has a long success hold.
 phase=0 if t<2.3 else 1 if t<4.45 else 2
 for i,(x,txt,col) in enumerate([(71,'01 OBSERVE',BLUE),(512,'02 REFLECT',PURPLE),(980,'03 RECOVER',TEAL)]):
  if i==1:continue
  active=i<=phase;c.text(x,471,('✓ ' if i<phase or done else '> ')+txt,12,col if active else '#A1AFC3',mono=True)


def frame(seconds):
 seconds%=SCENE*len(CASES);case_id=int(seconds//SCENE);t=seconds%SCENE
 c=Canvas();base(c,seconds);scene(c,case_id,t)
 if t>SCENE-.3:
  incoming=Canvas();base(incoming,seconds);scene(incoming,(case_id+1)%len(CASES),0)
  c.im=Image.blend(c.im,incoming.im,ease((t-(SCENE-.3))/.3))
 return c.image()

def preview(output):
 samples=[.7,1.7,3.5,5.9,7.8,13.5,17.8]
 board=Image.new('RGB',(1280,700*len(samples)),BG)
 for i,t in enumerate(samples):board.paste(frame(t),(0,i*700))
 board.save(output/'contact-sheet.png');frame(7.8).save(output/'poster.png')

def export(output):
 ff=shutil.which('ffmpeg')
 if not ff:raise SystemExit('ffmpeg is required for export.')
 with tempfile.TemporaryDirectory(prefix='agent-reflex-ascii-') as name:
  folder=Path(name);n=FPS*SCENE*len(CASES)
  for i in range(n):
   frame(i/FPS).save(folder/f'{i:04}.png')
   if i%FPS==0:print(f'Rendered {i//FPS:02}/{n//FPS} seconds',flush=True)
  subprocess.run([ff,'-hide_banner','-loglevel','error','-y','-framerate',str(FPS),'-i',str(folder/'%04d.png'),
   '-filter_complex','split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle',
   '-loop','0',str(output/'cover.gif')],check=True)
  subprocess.run([ff,'-hide_banner','-loglevel','error','-y','-framerate',str(FPS),'-i',str(folder/'%04d.png'),
   '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(output/'cover.mp4')],check=True)
 frame(7.8).save(output/'cover.png')
 # Replace the README's old line-icon logo with the generated paper-style face.
 head=sprite(0).crop((28*S,7*S,236*S,215*S)).resize((256,256),Image.Resampling.LANCZOS)
 head.save(ROOT/'assets/logo.png')
 print('Saved GIF, MP4, poster, and README mascot logo.',flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--preview',action='store_true');parser.add_argument('--output',type=Path,default=ROOT/'assets');parser.add_argument('--font')
 args=parser.parse_args();FONT_OVERRIDE=args.font;args.output.mkdir(parents=True,exist_ok=True)
 if args.preview:preview(args.output)
 else:export(args.output)
