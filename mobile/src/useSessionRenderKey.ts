import {useRef} from 'react';
import {resolveSessionRenderIdentity,SessionRenderIdentity} from './sessionRenderKey';

/**
 * Rotate component identity when an account/session scope changes without
 * placing the bearer token or other scope material in React's key string.
 */
export default function useSessionRenderKey(scope:string):string{
 const identity=useRef<SessionRenderIdentity|null>(null);
 identity.current=resolveSessionRenderIdentity(identity.current,scope);
 return identity.current.key;
}
