import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Modal,
  Pressable,
  Text,
  View,
} from "react-native";
import * as api from "./socialApi";
import {
  clampSocialPan,
  clampSocialZoom,
  nextSocialMediaIndex,
  normalizeSocialMediaItems,
  pinchSocialZoom,
  socialSwipeDirection,
} from "./socialMediaViewer";
import type { SocialMediaItem, SocialPan } from "./socialMediaViewer";

type Point = { x: number; y: number };
type Gesture =
  | {
      kind: "pinch";
      startDistance: number;
      startZoom: number;
    }
  | {
      kind: "single";
      startX: number;
      startY: number;
      lastX: number;
      lastY: number;
      startZoom: number;
      startPan: SocialPan;
    };

function touchPoints(event: any): Point[] {
  const touches = event?.nativeEvent?.touches;
  if (!Array.isArray(touches)) return [];
  return touches.slice(0, 2).map((touch: any) => ({
    x: Number(touch.pageX ?? touch.locationX),
    y: Number(touch.pageY ?? touch.locationY),
  })).filter((point: Point) => Number.isFinite(point.x) && Number.isFinite(point.y));
}

function distance(points: Point[]): number {
  if (points.length < 2) return 0;
  return Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y);
}

export default function NativeSocialMediaViewer({
  visible,
  token,
  media,
  initialIndex,
  onClose,
}: {
  visible: boolean;
  token: string;
  media: readonly SocialMediaItem[];
  initialIndex: number;
  onClose: () => void;
}) {
  const items = useMemo(() => normalizeSocialMediaItems(media), [media]);
  const itemsKey = items.map((item) => item.id).join(",");
  const [index, setIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<SocialPan>({ x: 0, y: 0 });
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const indexRef = useRef(0);
  const zoomRef = useRef(1);
  const panRef = useRef<SocialPan>({ x: 0, y: 0 });
  const stageRef = useRef({ width: 0, height: 0 });
  const imageRef = useRef({ width: 0, height: 0 });
  const gesture = useRef<Gesture | null>(null);
  const requestKey = items[index] ? `${items[index].id}:${attempt}:${token}` : "empty";
  const requestKeyRef = useRef(requestKey);
  requestKeyRef.current = requestKey;
  const active = items[index];

  function applyPan(x: number, y: number) {
    const next = clampSocialPan(
      x,
      y,
      stageRef.current.width,
      stageRef.current.height,
      imageRef.current.width,
      imageRef.current.height,
      zoomRef.current,
    );
    panRef.current = next;
    setPan(next);
  }

  function applyZoom(value: number) {
    const next = clampSocialZoom(value);
    zoomRef.current = next;
    setZoom(next);
    if (next <= 1) {
      panRef.current = { x: 0, y: 0 };
      setPan({ x: 0, y: 0 });
    } else {
      applyPan(panRef.current.x, panRef.current.y);
    }
  }

  function resetImageTransform() {
    zoomRef.current = 1;
    panRef.current = { x: 0, y: 0 };
    imageRef.current = { width: 0, height: 0 };
    gesture.current = null;
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  function changeBy(delta: number) {
    const next = nextSocialMediaIndex(indexRef.current, delta, items.length);
    if (next === null) return;
    indexRef.current = next;
    setIndex(next);
    resetImageTransform();
    setFailed(false);
    setLoading(true);
    setAttempt(0);
  }

  useEffect(() => {
    if (!visible) return;
    const start = items.length
      ? Math.max(0, Math.min(items.length - 1, Number.isSafeInteger(initialIndex) ? initialIndex : 0))
      : 0;
    indexRef.current = start;
    setIndex(start);
    resetImageTransform();
    setFailed(false);
    setLoading(items.length > 0);
    setAttempt(0);
    return () => {
      gesture.current = null;
    };
  }, [visible, token, initialIndex, itemsKey]);

  function onStageLayout(event: any) {
    const layout = event?.nativeEvent?.layout;
    const width = Number(layout?.width);
    const height = Number(layout?.height);
    if (!Number.isFinite(width) || !Number.isFinite(height)) return;
    stageRef.current = { width, height };
    applyPan(panRef.current.x, panRef.current.y);
  }

  function onTouchStart(event: any) {
    const points = touchPoints(event);
    if (points.length >= 2) {
      gesture.current = {
        kind: "pinch",
        startDistance: distance(points),
        startZoom: zoomRef.current,
      };
    } else if (points.length === 1) {
      gesture.current = {
        kind: "single",
        startX: points[0].x,
        startY: points[0].y,
        lastX: points[0].x,
        lastY: points[0].y,
        startZoom: zoomRef.current,
        startPan: panRef.current,
      };
    }
  }

  function onTouchMove(event: any) {
    const points = touchPoints(event);
    const current = gesture.current;
    if (current?.kind === "pinch" && points.length >= 2) {
      applyZoom(pinchSocialZoom(current.startZoom, current.startDistance, distance(points)));
      return;
    }
    if (current?.kind === "single" && points.length === 1) {
      current.lastX = points[0].x;
      current.lastY = points[0].y;
      if (current.startZoom > 1) {
        applyPan(
          current.startPan.x + current.lastX - current.startX,
          current.startPan.y + current.lastY - current.startY,
        );
      }
    }
  }

  function onTouchEnd(event: any) {
    const points = touchPoints(event);
    if (points.length === 1) {
      gesture.current = {
        kind: "single",
        startX: points[0].x,
        startY: points[0].y,
        lastX: points[0].x,
        lastY: points[0].y,
        startZoom: zoomRef.current,
        startPan: panRef.current,
      };
      return;
    }
    if (points.length > 1) return;
    const previous = gesture.current;
    gesture.current = null;
    if (previous?.kind === "single" && previous.startZoom <= 1 && zoomRef.current <= 1) {
      const direction = socialSwipeDirection(
        previous.lastX - previous.startX,
        previous.lastY - previous.startY,
        zoomRef.current,
      );
      if (direction) changeBy(direction);
    }
  }

  function retry() {
    setFailed(false);
    setLoading(true);
    setAttempt((value) => value + 1);
  }

  return (
    <Modal
      visible={visible}
      animationType="fade"
      presentationStyle="fullScreen"
      onRequestClose={onClose}
      statusBarTranslucent={false}
    >
      <View style={styles.page}>
        <View style={styles.header}>
          <Text accessibilityLiveRegion="polite" style={styles.position}>
            {items.length ? `${index + 1} / ${items.length}` : "Görsel yok"}
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Görseli kapat"
            hitSlop={12}
            onPress={onClose}
            style={styles.control}
          >
            <Text style={styles.controlText}>Kapat</Text>
          </Pressable>
        </View>
        <View
          style={styles.stage}
          onLayout={onStageLayout}
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
          onTouchCancel={() => { gesture.current = null; }}
        >
          {active && (
            <View key={requestKey} pointerEvents="none" style={{flex: 1}}>
            <Image
              source={api.socialImageSource(active.url, token)}
              resizeMode="contain"
              accessibilityLabel={`Gönderi görseli ${index + 1} / ${items.length}`}
              onLoad={(event: any) => {
                if (requestKeyRef.current !== requestKey) return;
                const source = event?.nativeEvent?.source;
                const width = Number(source?.width);
                const height = Number(source?.height);
                imageRef.current = {
                  width: Number.isFinite(width) ? width : 0,
                  height: Number.isFinite(height) ? height : 0,
                };
                setFailed(false);
                setLoading(false);
                applyPan(panRef.current.x, panRef.current.y);
              }}
              onError={() => {
                if (requestKeyRef.current !== requestKey) return;
                setLoading(false);
                setFailed(true);
              }}
              style={[
                styles.image,
                {
                  opacity: loading || failed ? 0 : 1,
                  transform: [
                    { translateX: pan.x },
                    { translateY: pan.y },
                    { scale: zoom },
                  ],
                },
              ]}
            />
            </View>
          )}
          {loading && <ActivityIndicator size="large" color="#FFFFFF" />}
          {failed && (
            <View style={styles.failure}>
              <Text style={styles.failureText}>Görsel açılamadı.</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Görseli yeniden yükle"
                onPress={retry}
                style={styles.control}
              >
                <Text style={styles.controlText}>Yeniden dene</Text>
              </Pressable>
            </View>
          )}
          {!active && <Text style={styles.failureText}>Görüntülenecek güvenli medya bulunamadı.</Text>}
        </View>
        <View style={styles.footer}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Önceki görsel"
            disabled={index <= 0 || items.length < 2}
            onPress={() => changeBy(-1)}
            style={[styles.control, (index <= 0 || items.length < 2) && styles.disabled]}
          >
            <Text style={styles.controlText}>‹</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Uzaklaştır"
            disabled={zoom <= 1}
            onPress={() => applyZoom(zoom - 0.5)}
            style={[styles.control, zoom <= 1 && styles.disabled]}
          >
            <Text style={styles.controlText}>−</Text>
          </Pressable>
          <Text accessibilityLabel="Yakınlaştırma" style={styles.zoomLabel}>
            {Math.round(zoom * 100)}%
          </Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Yakınlaştır"
            disabled={!active || zoom >= 5}
            onPress={() => applyZoom(zoom + 0.5)}
            style={[styles.control, (!active || zoom >= 5) && styles.disabled]}
          >
            <Text style={styles.controlText}>＋</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Görseli sığdır"
            disabled={zoom <= 1}
            onPress={() => applyZoom(1)}
            style={[styles.control, zoom <= 1 && styles.disabled]}
          >
            <Text style={styles.controlText}>Sığdır</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Sonraki görsel"
            disabled={index >= items.length - 1 || items.length < 2}
            onPress={() => changeBy(1)}
            style={[styles.control, (index >= items.length - 1 || items.length < 2) && styles.disabled]}
          >
            <Text style={styles.controlText}>›</Text>
          </Pressable>
        </View>
        <Text style={styles.hint}>İki parmakla yakınlaştırın; yakınlaştırılmış görseli sürükleyin.</Text>
      </View>
    </Modal>
  );
}

const styles = {
  page: {
    flex: 1,
    backgroundColor: "#090F19",
    paddingTop: 24,
    paddingBottom: 18,
  },
  header: {
    minHeight: 52,
    paddingHorizontal: 16,
    flexDirection: "row" as const,
    alignItems: "center" as const,
    justifyContent: "space-between" as const,
  },
  position: { color: "#FFFFFF", fontSize: 14, fontWeight: "700" as const },
  stage: {
    flex: 1,
    minHeight: 0,
    overflow: "hidden" as const,
    alignItems: "center" as const,
    justifyContent: "center" as const,
    backgroundColor: "#090F19",
  },
  image: { width: "100%" as const, height: "100%" as const },
  footer: {
    minHeight: 60,
    paddingHorizontal: 8,
    flexDirection: "row" as const,
    alignItems: "center" as const,
    justifyContent: "space-evenly" as const,
    gap: 4,
  },
  control: {
    minWidth: 44,
    minHeight: 44,
    paddingHorizontal: 10,
    alignItems: "center" as const,
    justifyContent: "center" as const,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#FFFFFF55",
    backgroundColor: "#172332",
  },
  controlText: { color: "#FFFFFF", fontSize: 16, fontWeight: "700" as const },
  zoomLabel: { minWidth: 42, color: "#FFFFFF", textAlign: "center" as const },
  disabled: { opacity: 0.35 },
  failure: { position: "absolute" as const, alignItems: "center" as const, gap: 12 },
  failureText: { color: "#FFFFFF", fontSize: 15, textAlign: "center" as const, paddingHorizontal: 20 },
  hint: { color: "#C8D2DF", fontSize: 12, textAlign: "center" as const, paddingTop: 4 },
};
