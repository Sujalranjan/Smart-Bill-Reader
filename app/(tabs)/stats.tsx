import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { listBills } from '../../lib/api';
import { formatMoney } from '../../lib/format';
import type { BillSummary } from '../../lib/types';

export default function StatsScreen() {
  const router = useRouter();
  const [data, setData] = useState<BillSummary[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await listBills());
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

      {bills.length === 0 && !error && <Text style={styles.empty}>No data yet. Scan a bill!</Text>}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
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
