import * as SecureStore from "expo-secure-store";
import { xchacha20poly1305 } from "@noble/ciphers/chacha.js";
import { randomBytes } from "@noble/ciphers/utils.js";
import { x25519 } from "@noble/curves/ed25519.js";
import { bytesToHex, hexToBytes } from "@noble/ciphers/utils.js";
import { hkdf } from "@noble/hashes/hkdf.js";
import { sha256 } from "@noble/hashes/sha2.js";

const VERSION = "x25519-xchacha20poly1305-v1";
const SECRET_KEY = "dai.e2ee.x25519.secret.v1";
const encoder = new TextEncoder();
const decoder = new TextDecoder();

export type E2EEEnvelope = {
  version: typeof VERSION;
  ephemeral_public_key: string;
  ciphertext: string;
};

function deriveMessageKey(shared: Uint8Array): Uint8Array {
  return hkdf(sha256, shared, new Uint8Array(32), encoder.encode("dental-ai/e2ee/message/v1"), 32);
}

export async function ensureIdentityKey(): Promise<{ publicKey: string; secretKey: string }> {
  const existing = await SecureStore.getItemAsync(SECRET_KEY);
  if (existing) {
    return { secretKey: existing, publicKey: bytesToHex(x25519.getPublicKey(hexToBytes(existing))) };
  }
  const pair = x25519.keygen();
  const secretKey = bytesToHex(pair.secretKey);
  await SecureStore.setItemAsync(SECRET_KEY, secretKey, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  return { secretKey, publicKey: bytesToHex(pair.publicKey) };
}

export async function encryptForRecipient(plaintext: string, recipientPublicKey: string): Promise<E2EEEnvelope> {
  const ephemeral = x25519.keygen();
  const shared = x25519.getSharedSecret(ephemeral.secretKey, hexToBytes(recipientPublicKey));
  const key = deriveMessageKey(shared);
  const nonce = randomBytes(24);
  const ciphertext = xchacha20poly1305(key, nonce).encrypt(encoder.encode(plaintext));
  const packed = new Uint8Array(nonce.length + ciphertext.length);
  packed.set(nonce);
  packed.set(ciphertext, nonce.length);
  return { version: VERSION, ephemeral_public_key: bytesToHex(ephemeral.publicKey), ciphertext: bytesToHex(packed) };
}

export async function decryptEnvelope(envelope: E2EEEnvelope, secretKey: string): Promise<string> {
  if (envelope.version !== VERSION) throw new Error("Desteklenmeyen mesaj şifreleme sürümü.");
  const packed = hexToBytes(envelope.ciphertext);
  if (packed.length <= 40) throw new Error("Geçersiz şifreli mesaj.");
  const shared = x25519.getSharedSecret(hexToBytes(secretKey), hexToBytes(envelope.ephemeral_public_key));
  const key = deriveMessageKey(shared);
  const plaintext = xchacha20poly1305(key, packed.slice(0, 24)).decrypt(packed.slice(24));
  return decoder.decode(plaintext);
}
