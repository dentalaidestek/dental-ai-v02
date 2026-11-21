// React Native Hermes ships no WebCrypto global, so any library that calls
// crypto.getRandomValues (@noble/hashes, @noble/ciphers — used by E2EE chat,
// the clinical media vault, academic file hashing and analysis uploads) fails
// with "crypto.getRandomValues must be defined" on device. expo-crypto ships
// a native implementation; expose it as the global before any other module
// loads. This file must be the first import in App.tsx.
import * as Crypto from 'expo-crypto';

type MinimalCrypto={getRandomValues?:(array:Uint8Array)=>Uint8Array;randomUUID?:()=>string};
const holder=globalThis as unknown as {crypto?:MinimalCrypto};
if(!holder.crypto)holder.crypto={};
if(typeof holder.crypto.getRandomValues!=='function')holder.crypto.getRandomValues=(array:Uint8Array)=>Crypto.getRandomValues(array);
if(typeof holder.crypto.randomUUID!=='function')holder.crypto.randomUUID=()=>Crypto.randomUUID();
