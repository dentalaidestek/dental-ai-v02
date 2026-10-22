const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
for(const rate of [16000,44100,48000]){
 let Processor;const packets=[];
 class Base{constructor(){this.port={postMessage:value=>packets.push(value)}}}
 vm.runInNewContext(fs.readFileSync('app/static/voice-pcm-worklet.js','utf8'),{AudioWorkletProcessor:Base,Int16Array,sampleRate:rate,registerProcessor:(name,cls)=>Processor=cls});
 const processor=new Processor();
 const length=Math.floor(rate*1.05);
 for(let at=0;at<length;at+=128)processor.process([[new Float32Array(Math.min(128,length-at)).fill(.5)]]);
 processor.port.onmessage({data:{type:'flush'}});
 const frames=packets.filter(p=>p instanceof ArrayBuffer);
 const samples=frames.reduce((sum,p)=>sum+p.byteLength/2,0);
 assert.ok(Math.abs(samples-16800)<=1,'Resampling rate '+rate);
 assert.ok(frames.every(p=>p.byteLength<=3200));
 assert.equal(new Int16Array(frames[0])[0],16384);
 assert.equal(packets.at(-1).type,'flushed');
}
console.log('PCM worklet: 16k/44.1k/48k resampling, bounded packets and final partial flush passed.');
