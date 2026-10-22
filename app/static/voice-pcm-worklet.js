/* PCM16 mono 16 kHz, bounded 100 ms packets. Never records to disk. */
class VoicePCM extends AudioWorkletProcessor {
  constructor(){super();this.phase=0;this.sum=0;this.count=0;this.frame=new Int16Array(1600);this.offset=0;this.port.onmessage=event=>{if(event.data?.type==='flush'){if(this.offset){const tail=this.frame.slice(0,this.offset);this.port.postMessage(tail.buffer,[tail.buffer]);this.offset=0}this.port.postMessage({type:'flushed'})}}}
  process(inputs){
    const input=inputs[0]?.[0];if(!input)return true;
    for(const sample of input){
      this.sum+=sample;this.count++;this.phase+=16000;
      if(this.phase>=sampleRate){
        const value=Math.max(-1,Math.min(1,this.sum/this.count));this.frame[this.offset++]=Math.round(value*(value<0?32768:32767));
        this.phase-=sampleRate;this.sum=0;this.count=0;
        if(this.offset===1600){this.port.postMessage(this.frame.buffer,[this.frame.buffer]);this.frame=new Int16Array(1600);this.offset=0}
      }
    }
    return true;
  }
}
registerProcessor('voice-pcm',VoicePCM);
