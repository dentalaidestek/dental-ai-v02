"""CPU runtime/blank-image rejection check, not a clinical benchmark."""
import hashlib,json,time,resource,sys
from pathlib import Path
import torch
from PIL import Image
from transformers import AutoImageProcessor,AutoModelForObjectDetection
root=Path(sys.argv[1]);out=Path(sys.argv[2]);torch.set_num_threads(2)
t=time.monotonic()
processor=AutoImageProcessor.from_pretrained(root,local_files_only=True,use_fast=False)
model,loading=AutoModelForObjectDetection.from_pretrained(root,local_files_only=True,output_loading_info=True)
model.eval();assert model.config.id2label[2]=='calculus'
report={'model':'Tesleum/shirdel-dental-stage2-conditions-v4','sha256':hashlib.sha256((root/'model.safetensors').read_bytes()).hexdigest(),'load_seconds':round(time.monotonic()-t,3),'loading_info':loading,'publisher_threshold':0.005,'clinical_validation':'NOT_VALIDATED','rows':[]}
samples=[('black',Image.new('RGB',(640,640),(0,0,0)),'synthetic_negative'),('white',Image.new('RGB',(640,640),(255,255,255)),'synthetic_negative'),('gray',Image.new('RGB',(640,640),(128,128,128)),'synthetic_negative')]
for p in sorted(Path('model-cache/test31').glob('*.jpg'))[:2]:samples.append((hashlib.sha256(p.read_bytes()).hexdigest(),Image.open(p).convert('RGB'),'unlabeled_for_calculus'))
for name,im,kind in samples:
 start=time.monotonic()
 with torch.inference_mode():pred=model(**processor(images=im,return_tensors='pt'))
 scores=pred.logits.sigmoid()[0,:,2]
 r=processor.post_process_object_detection(pred,threshold=.005,target_sizes=torch.tensor([[im.height,im.width]]))[0]
 mask=r['labels']==2
 row={'sample':name,'kind':kind,'calculus_max_score':float(scores.max()),'calculus_detections_at_0005':int(mask.sum()),'calculus_detections_at_025':int((scores>=.25).sum()),'seconds':round(time.monotonic()-start,3),'boxes':r['boxes'][mask].tolist(),'scores':r['scores'][mask].tolist()}
 report['rows'].append(row);out.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in row.items() if k not in ['boxes','scores']}),flush=True)
report['max_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1)
report['blank_rejection_pass']=all(r['calculus_detections_at_0005']==0 for r in report['rows'] if r['kind']=='synthetic_negative')
out.write_text(json.dumps(report,indent=2)+'\n')
