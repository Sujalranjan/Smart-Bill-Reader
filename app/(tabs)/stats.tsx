import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { getQualityReport, listBills } from '../../lib/api';
import { formatMoney, formatPercent, ISSUE_LABELS } from '../../lib/format';
import type { BillSummary, QualityReport } from '../../lib/types';

export default function StatsScreen() {
  const router = useRouter();
  const [data, setData] = useState<BillSummary[] | null>(null);
  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [bills, report] = await Promise.all([listBills(), getQualityReport()]);
      setData(bills);
      setQuality(report);
      setError(null);
    } catch (e: any) {
      setError(e.message ?? 'Analytics unavailable.');
    } finally {
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (data === null && !error) {
    return <View style={styles.center}><ActivityIndicator size="large" color="#4F46E5" /></View>;
  }

  const bills = data ?? [];
  const approved = bills.filter((b) => b.status === 'approved');
  const toReview = bills.length - approved.length;
  const approvedSpend = approved.reduce((sum, b) => sum + (b.total ?? 0), 0);
  const allSpend = bills.reduce((sum, b) => sum + (b.total ?? 0), 0);
  const suppliers = new Set(bills.map((b) => b.supplier.trim().toLowerCase())).size;
  const average = bills.length ? allSpend / bills.length : 0;

  return (
    <ScrollView style={styles.container} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}>
      {error && <Text style={styles.error}>{error} Pull down to retry.</Text>}

      <View style={styles.grid}>
        <View style={[styles.card, styles.cardFullWidth, { backgroundColor: '#4F46E5' }]}>
          <View>
            <Text style={styles.cardLabelLight}>Approved expenditure</Text>
            <Text style={styles.cardValueLight}>{formatMoney(approvedSpend)}</Text>
            <Text style={styles.cardSubLight}>{formatMoney(allSpend)} including bills not yet approved</Text>
          </View>
          <View style={[styles.iconCircle, { backgroundColor: 'rgba(255,255,255,0.2)' }]}>
            <Ionicons name="wallet" size={32} color="#FFF" />
          </View>
        </View>

        <TouchableOpacity style={[styles.card, styles.cardHalf]} onPress={() => router.push('/(tabs)/history')}>
          <View style={[styles.iconCircle, { backgroundColor: toReview ? '#FFFBEB' : '#ECFDF5' }]}>
            <Ionicons name={toReview ? 'alert-circle' : 'checkmark-done'} size={28} color={toReview ? '#D97706' : '#10B981'} />
          </View>
          <Text style={styles.cardValue}>{toReview}</Text>
          <Text style={styles.cardLabel}>Waiting for review</Text>
        </TouchableOpacity>

        <View style={[styles.card, styles.cardHalf]}>
          <View style={[styles.iconCircle, { backgroundColor: '#ECFDF5' }]}>
            <Ionicons name="receipt" size={28} color="#10B981" />
          </View>
          <Text style={styles.cardValue}>{bills.length}</Text>
          <Text style={styles.cardLabel}>Total bills</Text>
        </View>

        <View style={[styles.card, styles.cardHalf]}>
          <View style={[styles.iconCircle, { backgroundColor: '#EFF6FF' }]}>
            <Ionicons name="people" size={28} color="#2563EB" />
          </View>
          <Text style={styles.cardValue}>{suppliers}</Text>
          <Text style={styles.cardLabel}>Suppliers</Text>
        </View>

        <View style={[styles.card, styles.cardHalf]}>
          <View style={[styles.iconCircle, { backgroundColor: '#FFFBEB' }]}>
            <Ionicons name="stats-chart" size={28} color="#F59E0B" />
          </View>
          <Text style={styles.cardValue} numberOfLines={1} adjustsFontSizeToFit>{formatMoney(average)}</Text>
          <Text style={styles.cardLabel}>Average bill</Text>
        </View>
      </View>

      {quality && quality.bills_measured > 0 && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Processing quality</Text>
          <Text style={styles.sectionSub}>Based on {quality.bills_measured} scanned {quality.bills_measured === 1 ? 'bill' : 'bills'}</Text>
          <View style={styles.metricRow}>
            <Metric label="Approved automatically" value={formatPercent(quality.straight_through_rate)} />
            <Metric label="Needed review" value={formatPercent(quality.exception_rate)} />
            <Metric label="Needed correction" value={formatPercent(quality.manual_correction_rate)} />
          </View>
          <Text style={styles.sectionSub}>
            Average reading time: {quality.processing.avg_ocr_ms === null ? '—' : `${(quality.processing.avg_ocr_ms / 1000).toFixed(1)}s per bill`}
          </Text>
          {quality.exception_reasons.length > 0 && (
            <>
              <Text style={styles.reasonTitle}>Why bills needed review</Text>
              {quality.exception_reasons.slice(0, 5).map((r) => (
                <View key={r.code} style={styles.reasonRow}>
                  <Text style={styles.reasonText}>{ISSUE_LABELS[r.code] ?? r.code}</Text>
                  <Text style={styles.reasonCount}>{r.bills}</Text>
                </View>
              ))}
            </>
          )}
        </View>
      )}

      {bills.length === 0 && !error && <Text style={styles.empty}>No data yet. Scan a bill!</Text>}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { backgroundColor: '#FFF', marginHorizontal: 15, padding: 18, borderRadius: 20 },
  sectionTitle: { fontSize: 17, fontWeight: '800', color: '#111827' },
  sectionSub: { fontSize: 12, color: '#9CA3AF', marginTop: 4 },
  metricRow: { flexDirection: 'row', gap: 8, marginTop: 14, marginBottom: 6 },
  metric: { flex: 1, backgroundColor: '#F9FAFB', borderRadius: 12, padding: 10 },
  metricValue: { fontSize: 22, fontWeight: '800', color: '#111827' },
  metricLabel: { fontSize: 11, color: '#6B7280', marginTop: 2 },
  reasonTitle: { fontSize: 13, fontWeight: '700', color: '#6B7280', marginTop: 14, marginBottom: 4 },
  reasonRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  reasonText: { color: '#374151', fontSize: 14, flex: 1 },
  reasonCount: { color: '#111827', fontWeight: '700' },
  container: { flex: 1, backgroundColor: '#F3F4F6' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  error: { color: '#B91C1C', margin: 16, textAlign: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', padding: 15, justifyContent: 'space-between' },
  card: {
    backgroundColor: '#FFF', padding: 20, borderRadius: 20, marginBottom: 15,
    shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 5, elevation: 2,
  },
  cardFullWidth: { width: '100%', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardHalf: { width: '48%', alignItems: 'flex-start' },
  iconCircle: { width: 50, height: 50, borderRadius: 25, justifyContent: 'center', alignItems: 'center', marginBottom: 10 },
  cardLabel: { fontSize: 14, color: '#6B7280', fontWeight: '600' },
  cardValue: { fontSize: 24, color: '#111827', fontWeight: '800', marginBottom: 4 },
  cardLabelLight: { fontSize: 14, color: '#E0E7FF', fontWeight: '600' },
  cardValueLight: { fontSize: 30, color: '#FFFFFF', fontWeight: '800' },
  cardSubLight: { fontSize: 12, color: '#C7D2FE', marginTop: 4 },
  empty: { textAlign: 'center', marginTop: 40, color: '#9CA3AF' },
});
