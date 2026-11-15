import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { StatusBadge } from '../../components/status-badge';
import { ApiError, approveBill, deleteBill, getBill, updateBill } from '../../lib/api';
import { FIELD_LABELS, formatDate, formatMoney, numberToInput, toInputDate } from '../../lib/format';
import type { Bill, BillHeader, BillTotals, EditableLine, Issue, LineItem } from '../../lib/types';

const HEADER_SECTIONS: { title: string; fields: (keyof BillHeader)[] }[] = [
  { title: 'Invoice', fields: ['invoice_id', 'invoice_date', 'due_date', 'purchase_order', 'payment_terms'] },
  { title: 'Supplier', fields: ['supplier_name', 'supplier_gstin', 'supplier_address', 'supplier_phone', 'supplier_email'] },
  { title: 'Buyer', fields: ['buyer_name', 'buyer_gstin'] },
];
const TOTAL_FIELDS: (keyof BillTotals)[] = ['sub_total', 'cgst_amount', 'sgst_amount', 'igst_amount', 'total_tax', 'total_amount'];
const LINE_NUMBER_FIELDS: { key: keyof LineItem; label: string }[] = [
  { key: 'quantity', label: 'Qty' },
  { key: 'rate', label: 'Rate' },
  { key: 'discount_pct', label: 'Disc %' },
  { key: 'cgst_pct', label: 'CGST %' },
  { key: 'sgst_pct', label: 'SGST %' },
  { key: 'amount', label: 'Amount' },
];
const EMPTY_LINE: EditableLine = {
  description: '', hsn_sac: '', quantity: '', rate: '', discount_pct: '', cgst_pct: '',
  cgst_amount: '', sgst_pct: '', sgst_amount: '', amount: '',
};

type Form = {
  header: Record<keyof BillHeader, string>;
  totals: Record<keyof BillTotals, string>;
  lines: EditableLine[];
};

function toForm(bill: Bill): Form {
  const header = {} as Form['header'];
  (Object.keys(bill.header) as (keyof BillHeader)[]).forEach((k) => {
    header[k] = k === 'invoice_date' || k === 'due_date' ? toInputDate(bill.header[k]) : bill.header[k] ?? '';
  });
  const totals = {} as Form['totals'];
  TOTAL_FIELDS.forEach((k) => (totals[k] = numberToInput(bill.totals[k])));
  const lines = bill.line_items.map((item) => {
    const line = { ...EMPTY_LINE };
    (Object.keys(EMPTY_LINE) as (keyof LineItem)[]).forEach((k) => {
      const v = item[k];
      line[k] = typeof v === 'number' ? numberToInput(v) : v ?? '';
    });
    return line;
  });
  return { header, totals, lines };
}

function toNumber(text: string): number {
  const n = parseFloat(text.replace(/[₹,\s]/g, ''));
  return Number.isFinite(n) ? n : 0;
}

export default function ReviewBillScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const navigation = useNavigation();

  const [bill, setBill] = useState<Bill | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [badField, setBadField] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const leavingRef = useRef(false);

  const applyBill = useCallback((b: Bill) => {
    setBill(b);
    setForm(toForm(b));
    setDirty(false);
    setBadField(null);
  }, []);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      applyBill(await getBill(id));
    } catch (e: any) {
      setLoadError(e.message ?? 'Could not load this bill.');
    }
  }, [id, applyBill]);

  useEffect(() => {
    load();
  }, [load]);

  // Warn before leaving with unsaved corrections
  useEffect(() => {
    const unsubscribe = navigation.addListener('beforeRemove', (e: any) => {
      if (!dirty || leavingRef.current) return;
      e.preventDefault();
      Alert.alert('Discard changes?', 'Your corrections have not been saved.', [
        { text: 'Keep editing', style: 'cancel' },
        { text: 'Discard', style: 'destructive', onPress: () => navigation.dispatch(e.data.action) },
      ]);
    });
    return unsubscribe;
  }, [navigation, dirty]);

  const issuesByField = useMemo(() => {
    const map: Record<string, Issue['severity']> = {};
    bill?.issues.forEach((i) => {
      if (map[i.field] !== 'error') map[i.field] = i.severity;
    });
    return map;
  }, [bill]);

  const lineSum = useMemo(
    () => (form ? form.lines.reduce((sum, l) => sum + toNumber(l.amount), 0) : 0),
    [form],
  );

  if (loadError) {
    return (
      <View style={styles.center}>
        <Ionicons name="cloud-offline-outline" size={48} color="#9CA3AF" />
        <Text style={styles.muted}>{loadError}</Text>
        <TouchableOpacity style={[styles.button, styles.secondary, { marginTop: 16 }]} onPress={load}>
          <Text style={styles.secondaryText}>Try again</Text>
        </TouchableOpacity>
      </View>
    );
  }
  if (!bill || !form) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#4F46E5" />
      </View>
    );
  }

  const edit = (mutate: (f: Form) => void) => {
    setForm((prev) => {
      if (!prev) return prev;
      const next: Form = { header: { ...prev.header }, totals: { ...prev.totals }, lines: prev.lines.map((l) => ({ ...l })) };
      mutate(next);
      return next;
    });
    setDirty(true);
  };

  const payload = () => ({ header: form.header, totals: form.totals, line_items: form.lines });

  const handleError = (e: any) => {
    if (e instanceof ApiError && e.bill) applyBill(e.bill);
    if (e instanceof ApiError && e.field) setBadField(e.field);
    Alert.alert('Not saved', e.message ?? 'Something went wrong.');
  };

  const save = async (): Promise<boolean> => {
    setBusy('save');
    try {
      applyBill(await updateBill(bill.id, payload()));
      return true;
    } catch (e) {
      handleError(e);
      return false;
    } finally {
      setBusy(null);
    }
  };

  const approve = async () => {
    if (dirty && !(await save())) return;
    setBusy('approve');
    try {
      applyBill(await approveBill(bill.id));
      Alert.alert('Approved', 'This bill is now included in approved exports.');
    } catch (e: any) {
      if (e instanceof ApiError && e.bill) applyBill(e.bill);
      Alert.alert('Cannot approve yet', e.message);
    } finally {
      setBusy(null);
    }
  };

  const remove = () => {
    Alert.alert('Delete this bill?', 'The scan and its data will be permanently removed.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          setBusy('delete');
          try {
            await deleteBill(bill.id);
            leavingRef.current = true;
            router.back();
          } catch (e: any) {
            Alert.alert('Could not delete', e.message);
          } finally {
            setBusy(null);
          }
        },
      },
    ]);
  };

  const fieldStyle = (key: string) => {
    if (badField === key || issuesByField[key] === 'error') return styles.inputError;
    if (issuesByField[key] === 'warning') return styles.inputWarning;
    return null;
  };

  const isImage = (bill.mime_type ?? '').startsWith('image/');
  const errors = bill.issues.filter((i) => i.severity === 'error');
  const warnings = bill.issues.filter((i) => i.severity === 'warning');
  const total = toNumber(form.totals.total_amount);
  const lineSumMatches = form.lines.length === 0 || Math.abs(lineSum - total) <= 1 ||
    Math.abs(lineSum - toNumber(form.totals.sub_total)) <= 1 ||
    Math.abs(lineSum - (total - toNumber(form.totals.total_tax))) <= 1;

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
      <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 120 }} keyboardShouldPersistTaps="handled">
        {/* Status + original document */}
        <View style={styles.topCard}>
          <TouchableOpacity
            onPress={() => (isImage ? setPreviewOpen(true) : bill.image_url && Linking.openURL(bill.image_url))}
            style={styles.thumbWrap}
          >
            {isImage && bill.image_url ? (
              <Image source={{ uri: bill.image_url }} style={styles.thumb} />
            ) : (
              <View style={[styles.thumb, styles.pdfThumb]}>
                <Ionicons name="document-text" size={32} color="#DC2626" />
                <Text style={styles.pdfLabel}>PDF</Text>
              </View>
            )}
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <StatusBadge bill={bill} />
            <Text style={styles.topTitle} numberOfLines={2}>{bill.header.supplier_name || 'Unknown supplier'}</Text>
            <Text style={styles.muted}>
              {formatDate(bill.header.invoice_date)} · {formatMoney(bill.totals.total_amount)}
            </Text>
            <Text style={styles.small}>
              {bill.file_name ?? 'Scan'}{bill.page_count && bill.page_count > 1 ? ` · ${bill.page_count} pages` : ''} · tap to view original
            </Text>
          </View>
        </View>

        {/* Problems found by validation */}
        {(errors.length > 0 || warnings.length > 0) && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Please check</Text>
            {[...errors, ...warnings].map((issue, i) => (
              <View key={i} style={styles.issueRow}>
                <Ionicons
                  name={issue.severity === 'error' ? 'close-circle' : 'alert-circle'}
                  size={18}
                  color={issue.severity === 'error' ? '#DC2626' : '#D97706'}
                />
                <Text style={styles.issueText}>
                  {FIELD_LABELS[issue.field] && !issue.message.includes(FIELD_LABELS[issue.field])
                    ? `${FIELD_LABELS[issue.field]}: ` : ''}
                  {issue.message}
                </Text>
              </View>
            ))}
            {errors.length > 0 && <Text style={styles.small}>Red items must be fixed before the bill can be approved.</Text>}
          </View>
        )}

        {HEADER_SECTIONS.map((section) => (
          <View key={section.title} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            {section.fields.map((key) => (
              <View key={key} style={styles.field}>
                <Text style={styles.label}>
                  {FIELD_LABELS[key]}
                  {key.endsWith('date') ? ' (DD/MM/YYYY)' : ''}
                </Text>
                <TextInput
                  style={[styles.input, fieldStyle(key), key === 'supplier_address' && { minHeight: 60 }]}
                  value={form.header[key]}
                  multiline={key === 'supplier_address'}
                  autoCapitalize={key.endsWith('gstin') ? 'characters' : 'sentences'}
                  keyboardType={key === 'supplier_email' ? 'email-address' : key === 'supplier_phone' ? 'phone-pad' : 'default'}
                  onChangeText={(t) => edit((f) => { f.header[key] = t; })}
                  placeholder="—"
                  placeholderTextColor="#D1D5DB"
                />
              </View>
            ))}
          </View>
        ))}

        {/* Line items */}
        <View style={styles.section}>
          <View style={styles.rowBetween}>
            <Text style={styles.sectionTitle}>Line items ({form.lines.length})</Text>
            <Text style={[styles.small, !lineSumMatches && { color: '#D97706', fontWeight: '700' }]}>
              Sum {formatMoney(lineSum)}
            </Text>
          </View>
          {form.lines.map((line, index) => (
            <View key={index} style={[styles.lineCard, issuesByField[`line_items[${index}].amount`] && styles.inputWarning]}>
              <View style={styles.rowBetween}>
                <Text style={styles.lineNo}>#{index + 1}</Text>
                <TouchableOpacity
                  onPress={() => edit((f) => { f.lines.splice(index, 1); })}
                  hitSlop={10}
                  accessibilityLabel={`Remove line ${index + 1}`}
                >
                  <Ionicons name="trash-outline" size={18} color="#9CA3AF" />
                </TouchableOpacity>
              </View>
              <TextInput
                style={[styles.input, fieldStyle(`line_items[${index}].description`)]}
                value={line.description}
                placeholder="Product name"
                placeholderTextColor="#D1D5DB"
                onChangeText={(t) => edit((f) => { f.lines[index].description = t; })}
              />
              <View style={styles.grid}>
                <View style={styles.gridCell}>
                  <Text style={styles.label}>HSN/SAC</Text>
                  <TextInput
                    style={styles.input}
                    value={line.hsn_sac}
                    onChangeText={(t) => edit((f) => { f.lines[index].hsn_sac = t; })}
                  />
                </View>
                {LINE_NUMBER_FIELDS.map(({ key, label }) => (
                  <View key={key} style={styles.gridCell}>
                    <Text style={styles.label}>{label}</Text>
                    <TextInput
                      style={[styles.input, fieldStyle(`line_items[${index}].${key}`)]}
                      value={line[key]}
                      keyboardType="decimal-pad"
                      onChangeText={(t) => edit((f) => { f.lines[index][key] = t; })}
                    />
                  </View>
                ))}
              </View>
            </View>
          ))}
          <TouchableOpacity style={[styles.button, styles.secondary]} onPress={() => edit((f) => { f.lines.push({ ...EMPTY_LINE }); })}>
            <Ionicons name="add" size={18} color="#4F46E5" />
            <Text style={styles.secondaryText}>Add line</Text>
          </TouchableOpacity>
        </View>

        {/* Totals */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Totals</Text>
          {TOTAL_FIELDS.map((key) => (
            <View key={key} style={[styles.field, styles.rowBetween]}>
              <Text style={[styles.label, { flex: 1 }, key === 'total_amount' && styles.totalLabel]}>{FIELD_LABELS[key]}</Text>
              <TextInput
                style={[styles.input, styles.amountInput, fieldStyle(key)]}
                value={form.totals[key]}
                keyboardType="decimal-pad"
                placeholder="—"
                placeholderTextColor="#D1D5DB"
                onChangeText={(t) => edit((f) => { f.totals[key] = t; })}
              />
            </View>
          ))}
        </View>

        {bill.audit.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>History</Text>
            {bill.audit.map((a, i) => (
              <Text key={i} style={styles.small}>
                {a.action === 'scanned' ? 'Scanned' : a.action === 'approved' ? 'Approved' : a.action === 'auto_approved' ? 'Approved automatically (no problems found, known supplier)' : `Edited (${(a.fields ?? []).map((f) => FIELD_LABELS[f] ?? f).join(', ')})`}
                {' · '}
                {new Date(a.at).toLocaleString()}
              </Text>
            ))}
          </View>
        )}

        <TouchableOpacity style={styles.deleteLink} onPress={remove} disabled={!!busy}>
          <Ionicons name="trash-outline" size={16} color="#DC2626" />
          <Text style={{ color: '#DC2626', fontWeight: '600' }}>Delete this bill</Text>
        </TouchableOpacity>
      </ScrollView>

      {/* Action bar */}
      <View style={styles.actionBar}>
        <TouchableOpacity
          style={[styles.button, styles.secondary, { flex: 1 }, (!dirty || !!busy) && styles.disabled]}
          onPress={save}
          disabled={!dirty || !!busy}
        >
          {busy === 'save' ? <ActivityIndicator color="#4F46E5" /> : <Text style={styles.secondaryText}>Save</Text>}
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.button, styles.primary, { flex: 2 }, (!!busy || (bill.status === 'approved' && !dirty)) && styles.disabled]}
          onPress={approve}
          disabled={!!busy || (bill.status === 'approved' && !dirty)}
        >
          {busy === 'approve' ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <Text style={styles.primaryText}>
              {bill.status === 'approved' && !dirty ? 'Approved' : dirty ? 'Save & Approve' : 'Approve'}
            </Text>
          )}
        </TouchableOpacity>
      </View>

      <Modal visible={previewOpen} transparent animationType="fade" onRequestClose={() => setPreviewOpen(false)}>
        <Pressable style={styles.previewBackdrop} onPress={() => setPreviewOpen(false)}>
          <Image source={{ uri: bill.image_url }} style={styles.previewImage} resizeMode="contain" />
          <Text style={{ color: '#FFF', marginTop: 12 }}>Tap anywhere to close</Text>
        </Pressable>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F3F4F6' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24, gap: 8 },
  topCard: { flexDirection: 'row', gap: 14, backgroundColor: '#FFF', margin: 16, marginBottom: 0, padding: 14, borderRadius: 16 },
  thumbWrap: { borderRadius: 12, overflow: 'hidden' },
  thumb: { width: 84, height: 108, borderRadius: 12, backgroundColor: '#E5E7EB' },
  pdfThumb: { justifyContent: 'center', alignItems: 'center', backgroundColor: '#FEF2F2' },
  pdfLabel: { color: '#DC2626', fontWeight: '800', marginTop: 4 },
  topTitle: { fontSize: 18, fontWeight: '800', color: '#111827', marginTop: 6 },
  muted: { color: '#6B7280', fontSize: 14, marginTop: 2, textAlign: 'left' },
  small: { color: '#9CA3AF', fontSize: 12, marginTop: 4 },
  section: { backgroundColor: '#FFF', marginHorizontal: 16, marginTop: 14, padding: 14, borderRadius: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: '#1F2937', marginBottom: 8 },
  issueRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', paddingVertical: 4 },
  issueText: { flex: 1, color: '#374151', fontSize: 14 },
  field: { marginBottom: 10 },
  label: { fontSize: 12, color: '#6B7280', fontWeight: '600', marginBottom: 4 },
  totalLabel: { fontSize: 15, color: '#111827', fontWeight: '800' },
  input: {
    borderWidth: 1, borderColor: '#E5E7EB', borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8,
    fontSize: 15, color: '#111827', backgroundColor: '#FAFAFA',
  },
  amountInput: { width: 150, textAlign: 'right' },
  inputError: { borderColor: '#DC2626', backgroundColor: '#FEF2F2' },
  inputWarning: { borderColor: '#F59E0B', backgroundColor: '#FFFBEB' },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  lineCard: { borderWidth: 1, borderColor: '#E5E7EB', borderRadius: 12, padding: 10, marginBottom: 10, gap: 8 },
  lineNo: { fontWeight: '700', color: '#6B7280' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -4 },
  gridCell: { width: '33.33%', paddingHorizontal: 4, marginBottom: 6 },
  button: { flexDirection: 'row', gap: 6, justifyContent: 'center', alignItems: 'center', paddingVertical: 14, borderRadius: 12 },
  primary: { backgroundColor: '#4F46E5' },
  primaryText: { color: '#FFF', fontWeight: '700', fontSize: 16 },
  secondary: { backgroundColor: '#EEF2FF' },
  secondaryText: { color: '#4F46E5', fontWeight: '700', fontSize: 16 },
  disabled: { opacity: 0.5 },
  actionBar: {
    position: 'absolute', left: 0, right: 0, bottom: 0, flexDirection: 'row', gap: 10, padding: 14,
    paddingBottom: Platform.OS === 'ios' ? 30 : 14, backgroundColor: '#FFF', borderTopWidth: 1, borderTopColor: '#E5E7EB',
  },
  deleteLink: { flexDirection: 'row', gap: 6, alignItems: 'center', justifyContent: 'center', marginTop: 24 },
  previewBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.92)', justifyContent: 'center', alignItems: 'center' },
  previewImage: { width: '100%', height: '85%' },
});
