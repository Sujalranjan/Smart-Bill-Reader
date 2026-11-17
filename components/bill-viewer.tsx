import { Ionicons } from '@expo/vector-icons';
import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, LayoutChangeEvent, Linking, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import type { BillPage, FieldLocation } from '../lib/types';

const MIN_SCALE = 1;
const MAX_SCALE = 6;

type Props = {
  pages: BillPage[];
  /** Box to highlight; the viewer switches to its page and zooms to it. */
  highlight: FieldLocation | null;
  /** Fallback when there is no page image (older PDF bills). */
  originalUrl?: string;
};

/**
 * Shows the bill so a reviewer can compare it with the extracted values.
 * Pinch to zoom, drag to move, double-tap to zoom in or reset.
 */
export function BillViewer({ pages, highlight, originalUrl }: Props) {
  const [pageIndex, setPageIndex] = useState(0);
  const [frame, setFrame] = useState({ width: 0, height: 0 });
  const [naturalSizes, setNaturalSizes] = useState<Record<number, { width: number; height: number }>>({});
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const page = pages[pageIndex];

  // Older photo bills don't store their size; read it from the image.
  useEffect(() => {
    if (!page || (page.width && page.height) || naturalSizes[pageIndex]) return;
    Image.getSize(
      page.url,
      (width, height) => setNaturalSizes((s) => ({ ...s, [pageIndex]: { width, height } })),
      () => setFailed(true),
    );
  }, [page, pageIndex, naturalSizes]);

  const natural = page?.width && page?.height ? { width: page.width, height: page.height } : naturalSizes[pageIndex];

  // Size of the page when fitted inside the frame ("contain").
  const fitted = useMemo(() => {
    if (!natural || !frame.width || !frame.height) return null;
    const ratio = Math.min(frame.width / natural.width, frame.height / natural.height);
    return { width: natural.width * ratio, height: natural.height * ratio };
  }, [natural, frame]);

  const scale = useSharedValue(1);
  const tx = useSharedValue(0);
  const ty = useSharedValue(0);
  const start = useSharedValue({ scale: 1, x: 0, y: 0 });
  const bounds = useSharedValue({ fw: 0, fh: 0, cw: 0, ch: 0 });

  useEffect(() => {
    bounds.value = { fw: frame.width, fh: frame.height, cw: fitted?.width ?? 0, ch: fitted?.height ?? 0 };
  }, [frame, fitted, bounds]);

  // Keep the page from being dragged out of view.
  const clampX = (x: number, s: number) => {
    'worklet';
    const max = Math.max(0, (bounds.value.cw * s - bounds.value.fw) / 2);
    return Math.min(max, Math.max(-max, x));
  };
  const clampY = (y: number, s: number) => {
    'worklet';
    const max = Math.max(0, (bounds.value.ch * s - bounds.value.fh) / 2);
    return Math.min(max, Math.max(-max, y));
  };

  const reset = () => {
    scale.value = withTiming(1);
    tx.value = withTiming(0);
    ty.value = withTiming(0);
  };

  // Zoom to the highlighted value whenever it changes.
  useEffect(() => {
    if (!highlight) return;
    if (highlight.page !== pageIndex && highlight.page < pages.length) {
      setPageIndex(highlight.page);
      return; // runs again once the new page is laid out
    }
    if (!fitted || highlight.page !== pageIndex) return;
    const [x0, y0, x1, y1] = highlight.box;
    const boxW = Math.max((x1 - x0) * fitted.width, 1);
    const boxH = Math.max((y1 - y0) * fitted.height, 1);
    const s = Math.min(4, Math.max(MIN_SCALE, Math.min((frame.width * 0.85) / boxW, (frame.height * 0.45) / boxH)));
    // Move the box centre to the frame centre (scaling happens around the page centre).
    const px = ((x0 + x1) / 2 - 0.5) * fitted.width;
    const py = ((y0 + y1) / 2 - 0.5) * fitted.height;
    const maxX = Math.max(0, (fitted.width * s - frame.width) / 2);
    const maxY = Math.max(0, (fitted.height * s - frame.height) / 2);
    scale.value = withTiming(s);
    tx.value = withTiming(Math.min(maxX, Math.max(-maxX, -px * s)));
    ty.value = withTiming(Math.min(maxY, Math.max(-maxY, -py * s)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlight, fitted, pageIndex]);

  const pinch = Gesture.Pinch()
    .onStart(() => {
      start.value = { scale: scale.value, x: tx.value, y: ty.value };
    })
    .onUpdate((e) => {
      const s = Math.min(MAX_SCALE, Math.max(MIN_SCALE, start.value.scale * e.scale));
      scale.value = s;
      tx.value = clampX(start.value.x * (s / start.value.scale), s);
      ty.value = clampY(start.value.y * (s / start.value.scale), s);
    });

  const pan = Gesture.Pan()
    .averageTouches(true)
    .onStart(() => {
      start.value = { scale: scale.value, x: tx.value, y: ty.value };
    })
    .onUpdate((e) => {
      tx.value = clampX(start.value.x + e.translationX, scale.value);
      ty.value = clampY(start.value.y + e.translationY, scale.value);
    });

  const doubleTap = Gesture.Tap()
    .numberOfTaps(2)
    .onEnd(() => {
      if (scale.value > 1.05) {
        scale.value = withTiming(1);
        tx.value = withTiming(0);
        ty.value = withTiming(0);
      } else {
        scale.value = withTiming(2.5);
      }
    });

  const gesture = Gesture.Race(doubleTap, Gesture.Simultaneous(pinch, pan));

  const pageStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: tx.value }, { translateY: ty.value }, { scale: scale.value }],
  }));
  // Keep the highlight outline the same thickness at any zoom level.
  const outlineStyle = useAnimatedStyle(() => ({ borderWidth: 2.5 / scale.value }));

  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    setFrame({ width, height });
  };

  const goToPage = (index: number) => {
    setPageIndex(index);
    setLoading(true);
    setFailed(false);
    reset();
  };

  if (!pages.length) {
    return (
      <View style={[styles.frame, styles.center]}>
        <Ionicons name="document-text-outline" size={36} color="#9CA3AF" />
        <Text style={styles.note}>No preview for this bill.</Text>
        {originalUrl ? (
          <TouchableOpacity style={styles.openButton} onPress={() => Linking.openURL(originalUrl)}>
            <Text style={styles.openText}>Open original</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    );
  }

  const box = highlight && highlight.page === pageIndex && fitted ? highlight.box : null;

  return (
    <View style={styles.frame} onLayout={onLayout}>
      <GestureDetector gesture={gesture}>
        <View style={styles.center} collapsable={false}>
          {fitted && !failed ? (
            <Animated.View style={[{ width: fitted.width, height: fitted.height }, pageStyle]}>
              <Image
                source={{ uri: page.url }}
                style={{ width: fitted.width, height: fitted.height }}
                resizeMode="contain"
                onLoadEnd={() => setLoading(false)}
                onError={() => setFailed(true)}
              />
              {box && (
                <Animated.View
                  pointerEvents="none"
                  style={[
                    styles.highlight,
                    outlineStyle,
                    {
                      left: box[0] * fitted.width - 3,
                      top: box[1] * fitted.height - 3,
                      width: (box[2] - box[0]) * fitted.width + 6,
                      height: (box[3] - box[1]) * fitted.height + 6,
                    },
                  ]}
                />
              )}
            </Animated.View>
          ) : null}
          {failed ? (
            <View style={styles.center}>
              <Text style={styles.note}>Could not load the bill image.</Text>
              {originalUrl ? (
                <TouchableOpacity style={styles.openButton} onPress={() => Linking.openURL(originalUrl)}>
                  <Text style={styles.openText}>Open original</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          ) : (loading || !fitted) && (
            <ActivityIndicator style={StyleSheet.absoluteFill} color="#FFF" />
          )}
        </View>
      </GestureDetector>

      <View style={styles.toolbar} pointerEvents="box-none">
        {pages.length > 1 ? (
          <View style={styles.pager}>
            <TouchableOpacity disabled={pageIndex === 0} onPress={() => goToPage(pageIndex - 1)} hitSlop={8} accessibilityLabel="Previous page">
              <Ionicons name="chevron-back" size={18} color={pageIndex === 0 ? '#6B7280' : '#FFF'} />
            </TouchableOpacity>
            <Text style={styles.pagerText}>Page {pageIndex + 1} of {pages.length}</Text>
            <TouchableOpacity disabled={pageIndex === pages.length - 1} onPress={() => goToPage(pageIndex + 1)} hitSlop={8} accessibilityLabel="Next page">
              <Ionicons name="chevron-forward" size={18} color={pageIndex === pages.length - 1 ? '#6B7280' : '#FFF'} />
            </TouchableOpacity>
          </View>
        ) : <View />}
        <TouchableOpacity style={styles.fitButton} onPress={reset} accessibilityLabel="Show whole page">
          <Ionicons name="scan-outline" size={16} color="#FFF" />
          <Text style={styles.pagerText}>Whole page</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { flex: 1, backgroundColor: '#1F2937', overflow: 'hidden' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 8 },
  highlight: {
    position: 'absolute', borderColor: '#F59E0B', backgroundColor: 'rgba(245, 158, 11, 0.18)', borderRadius: 3,
  },
  note: { color: '#D1D5DB', fontSize: 14 },
  openButton: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: '#4F46E5' },
  openText: { color: '#FFF', fontWeight: '700' },
  toolbar: {
    position: 'absolute', left: 8, right: 8, bottom: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  pager: {
    flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 999, backgroundColor: 'rgba(17, 24, 39, 0.75)',
  },
  pagerText: { color: '#FFF', fontSize: 12, fontWeight: '600' },
  fitButton: {
    flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 999, backgroundColor: 'rgba(17, 24, 39, 0.75)',
  },
});
