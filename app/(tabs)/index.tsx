import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';
import { useRouter } from 'expo-router';
import * as Sharing from 'expo-sharing';
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

import { downloadExport, EXPORT_MIME, ExportFormat, scanBill, UploadFile } from '../../lib/api';
import { isoDate } from '../../lib/format';

const MAX_PAGES = 10;

type Period = 'all' | 'this_month' | 'last_month' | 'this_fy' | 'last_fy';
const PERIODS: { key: Period; label: string }[] = [
  { key: 'all', label: 'All time' },
  { key: 'this_month', label: 'This month' },
  { key: 'last_month', label: 'Last month' },
  { key: 'this_fy', label: 'This financial year' },
  { key: 'last_fy', label: 'Last financial year' },
];
const FORMATS: { key: ExportFormat; label: string; hint: string }[] = [
  { key: 'xlsx', label: 'Excel', hint: 'Summary, line items and one sheet per supplier' },
  { key: 'csv', label: 'CSV', hint: 'One row per line item, for import into accounting software' },
  { key: 'json', label: 'JSON', hint: 'Structured data for system integration' },
];

function periodRange(period: Period): { from?: string; to?: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  const fyStart = m >= 3 ? y : y - 1; // Indian financial year starts 1 April
  switch (period) {
    case 'this_month':
      return { from: isoDate(new Date(y, m, 1)), to: isoDate(new Date(y, m + 1, 0)) };
    case 'last_month':
      return { from: isoDate(new Date(y, m - 1, 1)), to: isoDate(new Date(y, m, 0)) };
    case 'this_fy':
      return { from: `${fyStart}-04-01`, to: `${fyStart + 1}-03-31` };
    case 'last_fy':
      return { from: `${fyStart - 1}-04-01`, to: `${fyStart}-03-31` };
    default:
      return {};
  }
}

function fromAsset(asset: ImagePicker.ImagePickerAsset, index: number): UploadFile {
  const ext = (asset.fileName?.split('.').pop() || asset.uri.split('.').pop() || 'jpg').toLowerCase();
  return {
    uri: asset.uri,
    name: asset.fileName ?? `page-${index + 1}.${ext}`,
    mimeType: asset.mimeType ?? (ext === 'png' ? 'image/png' : 'image/jpeg'),
  };
}

export default function ScanScreen() {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [format, setFormat] = useState<ExportFormat>('xlsx');
  const [period, setPeriod] = useState<Period>('all');
  const [approvedOnly, setApprovedOnly] = useState(true);

  const upload = async (files: UploadFile[]) => {
    setBusy(files.length > 1 ? `Reading ${files.length} pages…` : 'Reading your bill…');
    try {
      const result = await scanBill(files);
      const open = () => router.push({ pathname: '/bill/[id]', params: { id: result.id } });
      if (result.auto_approved) {
        // Standard invoice from a known supplier: nothing to review.
        Alert.alert(
          'Approved automatically',
          `${result.bill.header.supplier_name ?? 'Bill'} · ${result.bill.header.invoice_id ?? ''}\nNo problems were found, so no review is needed.`,
          [{ text: 'View bill', onPress: open }, { text: 'Scan another', style: 'cancel' }],
        );
      } else {
        open();
      }
    } catch (e: any) {
      Alert.alert('Could not scan', e.message ?? 'Please try again.');
    } finally {
      setBusy(null);
    }
  };

  // Camera: one photo per page; the user can add pages of the same bill.
  const openCamera = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Camera access needed', 'Allow camera access in Settings to scan bills.');
      return;
    }
    const pages: UploadFile[] = [];
    const capture = async () => {
      const res = await ImagePicker.launchCameraAsync({ quality: 0.85 });
      if (res.canceled) {
        if (pages.length) upload(pages);
        return;
      }
      pages.push(fromAsset(res.assets[0], pages.length));
      if (pages.length >= MAX_PAGES) {
        upload(pages);
        return;
      }
      Alert.alert(`Page ${pages.length} captured`, 'Does this bill have another page?', [
        { text: 'Add page', onPress: capture },
        { text: 'Done', style: 'cancel', onPress: () => upload(pages) },
      ]);
    };
    capture();
  };

  // Gallery: pick one photo, or several photos that are pages of one bill.
  const openGallery = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      selectionLimit: MAX_PAGES,
      quality: 1,
    });
    if (!res.canceled && res.assets.length) upload(res.assets.map(fromAsset));
  };

  const openDocument = async () => {
    const res = await DocumentPicker.getDocumentAsync({
      type: ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff'],
      copyToCacheDirectory: true,
    });
    if (res.canceled || !res.assets?.length) return;
    const a = res.assets[0];
    upload([{ uri: a.uri, name: a.name, mimeType: a.mimeType ?? 'application/pdf' }]);
  };

  const runExport = async (mode: 'share' | 'save') => {
    setExportOpen(false);
    setBusy('Preparing export…');
    try {
      const uri = await downloadExport({ format, approvedOnly, ...periodRange(period) });
      const filename = uri.split('/').pop() ?? `SmartBill.${format}`;
      const mimeType = EXPORT_MIME[format];

      if (mode === 'save' && Platform.OS === 'android') {
        const { StorageAccessFramework } = FileSystem;
        const permission = await StorageAccessFramework.requestDirectoryPermissionsAsync();
        if (!permission.granted) return;
        const target = await StorageAccessFramework.createFileAsync(permission.directoryUri, filename.replace(/\.\w+$/, ''), mimeType);
        const data = await FileSystem.readAsStringAsync(uri, { encoding: FileSystem.EncodingType.Base64 });
        await FileSystem.writeAsStringAsync(target, data, { encoding: FileSystem.EncodingType.Base64 });
        Alert.alert('Saved', `${filename} was saved to the selected folder.`);
      } else if (await Sharing.isAvailableAsync()) {
        // On iOS "Save to Files" is part of the share sheet.
        await Sharing.shareAsync(uri, { mimeType, dialogTitle: 'Share bill report' });
      } else {
        Alert.alert('Sharing unavailable', 'This device cannot share files.');
      }
    } catch (e: any) {
      Alert.alert('Export failed', e.message ?? 'Please try again.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.cardContainer} showsVerticalScrollIndicator={false}>
        <Text style={styles.subtitle}>Scan a bill, check the details, then approve it.</Text>
        {busy ? (
          <View style={styles.loaderCard}>
            <ActivityIndicator size="large" color="#4F46E5" />
            <Text style={styles.loaderText}>{busy}</Text>
          </View>
        ) : (
          <>
            <ActionCard icon="camera" color="#4F46E5" bg="#EEF2FF" title="Scan with camera" sub="Multi-page bills supported" onPress={openCamera} primary />
            <ActionCard icon="images" color="#10B981" bg="#ECFDF5" title="Upload photos" sub="Pick one photo, or several pages of one bill" onPress={openGallery} />
            <ActionCard icon="document-text" color="#DC2626" bg="#FEF2F2" title="Upload PDF" sub="E-invoices and scanned PDFs" onPress={openDocument} />
            <ActionCard icon="download" color="#2563EB" bg="#EFF6FF" title="Export bills" sub="Excel, CSV or JSON, filtered by period" onPress={() => setExportOpen(true)} />
          </>
        )}
      </ScrollView>

      <Modal visible={exportOpen} transparent animationType="slide" onRequestClose={() => setExportOpen(false)}>
        <Pressable style={styles.backdrop} onPress={() => setExportOpen(false)} />
        <View style={styles.sheet}>
          <Text style={styles.sheetTitle}>Export bills</Text>

          <Text style={styles.sheetLabel}>Format</Text>
          {FORMATS.map((f) => (
            <TouchableOpacity key={f.key} style={[styles.option, format === f.key && styles.optionActive]} onPress={() => setFormat(f.key)}>
              <Ionicons name={format === f.key ? 'radio-button-on' : 'radio-button-off'} size={20} color="#4F46E5" />
              <View style={{ flex: 1 }}>
                <Text style={styles.optionTitle}>{f.label}</Text>
                <Text style={styles.optionHint}>{f.hint}</Text>
              </View>
            </TouchableOpacity>
          ))}

          <Text style={styles.sheetLabel}>Invoice date</Text>
          <View style={styles.chips}>
            {PERIODS.map((p) => (
              <TouchableOpacity key={p.key} style={[styles.chip, period === p.key && styles.chipActive]} onPress={() => setPeriod(p.key)}>
                <Text style={[styles.chipText, period === p.key && styles.chipTextActive]}>{p.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.optionTitle}>Approved bills only</Text>
              <Text style={styles.optionHint}>Leave on for accounting imports</Text>
            </View>
            <Switch value={approvedOnly} onValueChange={setApprovedOnly} />
          </View>

          <View style={styles.sheetButtons}>
            <TouchableOpacity style={[styles.button, styles.secondary]} onPress={() => runExport('share')}>
              <Ionicons name="share-social" size={18} color="#4F46E5" />
              <Text style={styles.secondaryText}>Share</Text>
            </TouchableOpacity>
            {Platform.OS === 'android' && (
              <TouchableOpacity style={[styles.button, styles.primary]} onPress={() => runExport('save')}>
                <Ionicons name="download" size={18} color="#FFF" />
                <Text style={styles.primaryText}>Save to device</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}

function ActionCard(props: {
  icon: keyof typeof Ionicons.glyphMap; color: string; bg: string; title: string; sub: string;
  onPress: () => void; primary?: boolean;
}) {
  return (
    <TouchableOpacity style={[styles.card, props.primary && styles.cardPrimary]} onPress={props.onPress}>
      <View style={[styles.iconCircle, { backgroundColor: props.bg }]}>
        <Ionicons name={props.icon} size={30} color={props.color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{props.title}</Text>
        <Text style={styles.cardSub}>{props.sub}</Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F3F4F6', paddingHorizontal: 20 },
  subtitle: { fontSize: 15, color: '#6B7280', marginTop: 16, marginBottom: 4 },
  cardContainer: { gap: 14, paddingBottom: 40 },
  card: {
    backgroundColor: '#FFFFFF', padding: 18, borderRadius: 20, flexDirection: 'row', alignItems: 'center', gap: 16,
    shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 10, elevation: 2,
  },
  cardPrimary: { borderWidth: 1, borderColor: '#C7D2FE' },
  iconCircle: { width: 56, height: 56, borderRadius: 28, justifyContent: 'center', alignItems: 'center' },
  cardTitle: { fontSize: 17, fontWeight: '700', color: '#1F2937' },
  cardSub: { fontSize: 13, color: '#9CA3AF', marginTop: 2 },
  loaderCard: { backgroundColor: '#FFFFFF', padding: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  loaderText: { marginTop: 16, fontSize: 16, color: '#4F46E5', fontWeight: '600' },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: {
    backgroundColor: '#FFF', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20,
    paddingBottom: Platform.OS === 'ios' ? 36 : 20,
  },
  sheetTitle: { fontSize: 20, fontWeight: '800', color: '#111827' },
  sheetLabel: { fontSize: 13, fontWeight: '700', color: '#6B7280', marginTop: 16, marginBottom: 8, textTransform: 'uppercase' },
  option: { flexDirection: 'row', gap: 10, alignItems: 'center', padding: 10, borderRadius: 12 },
  optionActive: { backgroundColor: '#EEF2FF' },
  optionTitle: { fontSize: 15, fontWeight: '600', color: '#1F2937' },
  optionHint: { fontSize: 12, color: '#9CA3AF' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999, backgroundColor: '#F3F4F6' },
  chipActive: { backgroundColor: '#4F46E5' },
  chipText: { color: '#374151', fontWeight: '600', fontSize: 13 },
  chipTextActive: { color: '#FFF' },
  switchRow: { flexDirection: 'row', alignItems: 'center', marginTop: 18 },
  sheetButtons: { flexDirection: 'row', gap: 10, marginTop: 20 },
  button: { flex: 1, flexDirection: 'row', gap: 6, justifyContent: 'center', alignItems: 'center', paddingVertical: 14, borderRadius: 12 },
  primary: { backgroundColor: '#4F46E5' },
  primaryText: { color: '#FFF', fontWeight: '700', fontSize: 15 },
  secondary: { backgroundColor: '#EEF2FF' },
  secondaryText: { color: '#4F46E5', fontWeight: '700', fontSize: 15 },
});
