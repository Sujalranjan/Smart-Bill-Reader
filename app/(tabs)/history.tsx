import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Image, RefreshControl, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { StatusBadge } from '../../components/status-badge';
import { listBills } from '../../lib/api';
import { formatDate, formatMoney } from '../../lib/format';
import type { BillSummary } from '../../lib/types';

type Filter = 'all' | 'review' | 'approved';
const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'review', label: 'To review' },
  { key: 'approved', label: 'Approved' },
];

export default function HistoryScreen() {
  const router = useRouter();
  const [bills, setBills] = useState<BillSummary[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setBills(await listBills());
      setError(null);
    } catch (e: any) {
      setError(e.message ?? 'Could not load your bills.');
    } finally {
      setRefreshing(false);
    }
  }, []);

  // Reload whenever the tab is shown (e.g. after reviewing a bill)
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const visible = useMemo(() => {
    if (!bills) return [];
    if (filter === 'approved') return bills.filter((b) => b.status === 'approved');
    if (filter === 'review') return bills.filter((b) => b.status !== 'approved');
    return bills;
  }, [bills, filter]);

  const toReview = bills?.filter((b) => b.status !== 'approved').length ?? 0;

  if (bills === null && !error) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#4F46E5" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.filters}>
        {FILTERS.map((f) => (
          <TouchableOpacity
            key={f.key}
            style={[styles.chip, filter === f.key && styles.chipActive]}
            onPress={() => setFilter(f.key)}
          >
            <Text style={[styles.chipText, filter === f.key && styles.chipTextActive]}>
              {f.label}{f.key === 'review' && toReview > 0 ? ` (${toReview})` : ''}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {error && (
        <TouchableOpacity style={styles.errorBanner} onPress={load}>
          <Ionicons name="cloud-offline-outline" size={18} color="#B91C1C" />
          <Text style={styles.errorText}>{error} Tap to retry.</Text>
        </TouchableOpacity>
      )}

      <FlatList
        data={visible}
        keyExtractor={(item) => item.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        contentContainerStyle={visible.length === 0 ? { flex: 1 } : { paddingBottom: 20 }}
        ListEmptyComponent={
          <View style={styles.center}>
            <Ionicons name="receipt-outline" size={64} color="#D1D5DB" />
            <Text style={styles.emptyText}>
              {filter === 'review' ? 'Nothing waiting for review' : filter === 'approved' ? 'No approved bills yet' : 'No bills scanned yet'}
            </Text>
          </View>
        }
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.card} onPress={() => router.push({ pathname: '/bill/[id]', params: { id: item.id } })}>
            {item.image ? (
              <Image source={{ uri: item.image }} style={styles.image} />
            ) : (
              <View style={[styles.image, styles.placeholder]}>
                <Ionicons name={item.mime_type === 'application/pdf' ? 'document-text' : 'image-outline'} size={22} color="#9CA3AF" />
              </View>
            )}
            <View style={styles.info}>
              <Text style={styles.supplier} numberOfLines={1}>{item.supplier}</Text>
              <Text style={styles.date}>
                {formatDate(item.invoice_date)}{item.invoice_id ? ` · #${item.invoice_id}` : ''}
              </Text>
              <View style={{ marginTop: 4 }}>
                <StatusBadge bill={item} />
              </View>
            </View>
            <View style={styles.amountContainer}>
              <Text style={styles.amount}>{formatMoney(item.total)}</Text>
              <Text style={styles.items}>{item.items_count} items</Text>
            </View>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F3F4F6' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  filters: { flexDirection: 'row', gap: 8, paddingHorizontal: 20, paddingVertical: 12 },
  chip: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 999, backgroundColor: '#E5E7EB' },
  chipActive: { backgroundColor: '#4F46E5' },
  chipText: { color: '#374151', fontWeight: '600' },
  chipTextActive: { color: '#FFF' },
  errorBanner: { flexDirection: 'row', gap: 8, alignItems: 'center', marginHorizontal: 20, padding: 10, borderRadius: 10, backgroundColor: '#FEF2F2' },
  errorText: { color: '#B91C1C', flex: 1 },
  card: {
    flexDirection: 'row', backgroundColor: '#FFF', marginHorizontal: 20, marginTop: 12, padding: 12,
    borderRadius: 16, alignItems: 'center', shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 5, elevation: 2,
  },
  image: { width: 52, height: 64, borderRadius: 10, marginRight: 12, backgroundColor: '#E5E7EB' },
  placeholder: { justifyContent: 'center', alignItems: 'center' },
  info: { flex: 1 },
  supplier: { fontSize: 16, fontWeight: '600', color: '#1F2937' },
  date: { fontSize: 12, color: '#9CA3AF', marginTop: 2 },
  amountContainer: { alignItems: 'flex-end', marginLeft: 8 },
  amount: { fontSize: 15, fontWeight: '700', color: '#059669' },
  items: { fontSize: 12, color: '#9CA3AF' },
  emptyText: { color: '#9CA3AF', marginTop: 10, fontSize: 16 },
});
