export type ClinicalMediaPickerAsset = {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  fileSize?: number | null;
};

export type NormalizedClinicalMediaAsset = {
  uri: string;
  name: string;
  type: 'image/jpeg' | 'image/png' | 'image/webp';
};

export const CLINICAL_MEDIA_PICKER_MAX_FILES = 12;
export const CLINICAL_MEDIA_PICKER_MAX_BYTES = 12 * 1024 * 1024;

const MIME_BY_EXTENSION: Record<string, NormalizedClinicalMediaAsset['type']> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
};
const EXTENSION_BY_MIME: Record<string, string> = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/webp': 'webp',
};

/**
 * Expo can return an opaque Android content:// URI without a filename.
 * Derive a safe extension from the declared MIME in that case; never silently
 * label PNG/WebP bytes as JPEG because the backend verifies extension vs bytes.
 */
export function normalizeClinicalMediaAssets(
  assets: ClinicalMediaPickerAsset[],
): NormalizedClinicalMediaAsset[] {
  if (!Array.isArray(assets) || assets.length < 1 || assets.length > CLINICAL_MEDIA_PICKER_MAX_FILES) {
    throw new Error('Tek seferde 1–12 klinik görüntü seçebilirsiniz.');
  }

  return assets.map((asset, index) => {
    if (!asset || typeof asset.uri !== 'string' || !asset.uri.trim() ||
        !/^(?:file|content):\/\//i.test(asset.uri) || /[\x00-\x1f]/.test(asset.uri) || asset.uri.includes('..')) {
      throw new Error('Klinik görüntü kaynağı geçersiz. Görüntüyü yeniden seçin.');
    }
    if (typeof asset.fileSize === 'number') {
      if (!Number.isFinite(asset.fileSize) || asset.fileSize < 0) {
        throw new Error('Klinik görüntü boyutu geçersiz. Görüntüyü yeniden seçin.');
      }
      if (asset.fileSize > CLINICAL_MEDIA_PICKER_MAX_BYTES) {
        throw new Error('Her klinik görüntü en fazla 12 MB olabilir.');
      }
    }

    const declaredMime = typeof asset.mimeType === 'string' ? asset.mimeType.trim().toLowerCase() : '';
    if (declaredMime && !Object.prototype.hasOwnProperty.call(EXTENSION_BY_MIME, declaredMime)) {
      throw new Error('Yalnızca JPEG, PNG veya WebP klinik görüntüleri yüklenebilir.');
    }

    const providedName = typeof asset.fileName === 'string' ? asset.fileName.trim() : '';
    if (providedName && (/[\/\\\x00-\x1f\x7f]/.test(providedName) || providedName.length > 255)) {
      throw new Error('Klinik görüntü dosya adı geçersiz.');
    }

    const nameExtension = providedName.match(/\.([a-zA-Z0-9]+)$/)?.[1]?.toLowerCase() || '';
    const uriPath = asset.uri.split(/[?#]/, 1)[0];
    const uriExtension = uriPath.match(/\.([a-zA-Z0-9]+)$/)?.[1]?.toLowerCase() || '';
    if (nameExtension && !Object.prototype.hasOwnProperty.call(MIME_BY_EXTENSION, nameExtension)) {
      throw new Error('Klinik görüntü dosya uzantısı desteklenmiyor.');
    }
    // When both sources expose a supported extension, disagreement is
    // ambiguous: do not guess which name describes the bytes being uploaded.
    if (nameExtension && uriExtension &&
        Object.prototype.hasOwnProperty.call(MIME_BY_EXTENSION, uriExtension) &&
        nameExtension !== uriExtension) {
      throw new Error('Dosya adı ve cihaz kaynağının uzantısı eşleşmiyor. Görüntüyü yeniden seçin.');
    }

    const extension = nameExtension ||
      (Object.prototype.hasOwnProperty.call(MIME_BY_EXTENSION, uriExtension) ? uriExtension : '') ||
      EXTENSION_BY_MIME[declaredMime] || '';
    if (!extension) {
      throw new Error('Klinik görüntünün dosya türü belirlenemedi. Görüntüyü yeniden seçin.');
    }

    const expectedMime = MIME_BY_EXTENSION[extension];
    if (declaredMime && declaredMime !== expectedMime) {
      throw new Error('Dosya adı ve görüntü türü eşleşmiyor. Görüntüyü yeniden seçin.');
    }

    const name = providedName
      ? (nameExtension ? providedName : `${providedName}.${extension}`)
      : `klinik-${index}.${extension}`;
    if (name.length > 255) throw new Error('Klinik görüntü dosya adı çok uzun.');

    return { uri: asset.uri, name, type: expectedMime };
  });
}
