import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from 'expo-router';
import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { createVendor, deleteVendor, listVendors, updateVendor } from '../../lib/api';
import { formatDate } from '../../lib/format';
import type { Vendor } from '../../lib/types';

type Draft = { id: string | null; name: string; gstin: string; address: string; phone: string; email: string; blocked: boolean };

const EMPTY: Draft = { id: null, name: '', gstin: '', address: '', phone: '', email: '', blocked: false };
const TEXT_FIELDS: { key: 'name' | 'gstin' | 'address' | 'phone' | 'email'; label: string }[] = [
  { key: 'name', label: 'Supplier name' },
  { key: 'gstin', label: 'GSTIN' },
  { key: 'address', label: 'Address' },
  { key: 'phone', label: 'Phone' },
  { key: 'email', label: 'Email' },
];

export default function VendorsScreen() {
  const [vendors, setVendors] = useState<Vendor[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setVendors(await listVendors());
      setError(null);
    } catch (e: any) {
      setError(e.message ?? 'Could not load vendors.');
    } finally {
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!vendors) return [];
    if (!q) return vendors;
    return vendors.filter((v) => [v.name, v.gstin].some((x) => (x ?? '').toLowerCase().includes(q)));
  }, [vendors, query]);

  const openEdit = (v: Vendor) =>
    setDraft({ id: v.id, name: v.name ?? '', gstin: v.gstin ?? '', address: v.address ?? '', phone: v.phone ?? '', email: v.email ?? '', blocked: v.blocked });

  const save = async () => {
    if (!draft) return;
    if (!draft.name.trim()) {
      Alert.alert('Name required', 'Enter the supplier name.');
      return;
    }
    setSaving(true);
    try {
      const { id, ...fields } = draft;
      if (id) await updateVendor(id, fields);
      else await createVendor(fields);
      setDraft(null);
      load();
    } catch (e: any) {
      Alert.alert('Not saved', e.message ?? 'Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const remove = () => {
    if (!draft?.id) return;
    const id = draft.id;
    Alert.alert('Remove this supplier?', 'Bills already scanned are kept. The next bill from this supplier will be treated as a new supplier.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteVendor(id);
            setDraft(null);
            load();
          } catch (e: any) {
            Alert.alert('Could not remove', e.message);
          }
        },
      },
    ]);
  };

  if (vendors === null && !error) {
    return <View style={styles.center}><ActivityIndicator size="large" color="#4F46E5" /></View>;
  }

  return (
    <View style={styles.container}>
      <View style={styles.topRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={18} color="#9CA3AF" />
          <TextInput
            style={styles.searchInput}
            value={query}
            onChangeText={setQuery}
            placeholder="Search name or GSTIN"
            placeholderTextColor="#9CA3AF"
            autoCorrect={false}
          />
        </View>
        <TouchableOpacity style={styles.addButton} onPress={() => setDraft({ ...EMPTY })} accessibilityLabel="Add supplier">
          <Ionicons name="add" size={24} color="#FFF" />
        </TouchableOpacity>
      </View>

      {error && (
        <TouchableOpacity style={styles.errorBanner} onPress={load}>
          <Text style={styles.errorText}>{error} Tap to retry.</Text>
        </TouchableOpacity>
      )}

      <FlatList
        data={visible}
        keyExtractor={(v) => v.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        contentContainerStyle={visible.length === 0 ? { flex: 1 } : { paddingBottom: 20 }}
        ListEmptyComponent={
          <View style={styles.center}>
            <Ionicons name="business-outline" size={64} color="#D1D5DB" />
            <Text style={styles.emptyTitle}>{query.trim() ? 'No suppliers match your search' : 'No suppliers yet'}</Text>
            {!query.trim() && (
              <Text style={styles.emptyText}>
                Suppliers are added here automatically when you approve their first bill. Later bills from a known supplier with no problems are approved without review.
              </Text>
            )}
          </View>
        }
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.card} onPress={() => openEdit(item)}>
            <View style={[styles.avatar, item.blocked && { backgroundColor: '#FEF2F2' }]}>
              <Ionicons name={item.blocked ? 'ban' : 'business'} size={20} color={item.blocked ? '#DC2626' : '#4F46E5'} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.name} numberOfLines={1}>{item.name ?? 'Unnamed supplier'}</Text>
              <Text style={styles.sub}>{item.gstin ?? 'No GSTIN'}</Text>
              <Text style={styles.sub}>
                {item.bill_count} {item.bill_count === 1 ? 'bill' : 'bills'}
                {item.last_seen ? ` · last ${formatDate(item.last_seen.slice(0, 10))}` : ''}
                {item.blocked ? ' · Blocked' : ''}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color="#D1D5DB" />
          </TouchableOpacity>
        )}
      />

      <Modal visible={draft !== null} animationType="slide" transparent onRequestClose={() => setDraft(null)}>
        <KeyboardAvoidingView style={styles.modalWrap} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View style={styles.sheet}>
            <View style={styles.rowBetween}>
              <Text style={styles.sheetTitle}>{draft?.id ? 'Edit supplier' : 'Add supplier'}</Text>
              <TouchableOpacity onPress={() => setDraft(null)} hitSlop={10} accessibilityLabel="Close">
                <Ionicons name="close" size={24} color="#6B7280" />
              </TouchableOpacity>
            </View>
            {draft && (
              <ScrollView keyboardShouldPersistTaps="handled">
                {TEXT_FIELDS.map(({ key, label }) => (
                  <View key={key} style={{ marginTop: 12 }}>
                    <Text style={styles.label}>{label}</Text>
                    <TextInput
                      style={[styles.input, key === 'address' && { minHeight: 60 }]}
                      value={draft[key]}
                      multiline={key === 'address'}
                      autoCapitalize={key === 'gstin' ? 'characters' : key === 'email' ? 'none' : 'words'}
                      keyboardType={key === 'email' ? 'email-address' : key === 'phone' ? 'phone-pad' : 'default'}
                      onChangeText={(t) => setDraft((d) => (d ? { ...d, [key]: t } : d))}
                    />
                  </View>
                ))}
                <View style={[styles.rowBetween, { marginTop: 16 }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.name}>Block this supplier</Text>
                    <Text style={styles.sub}>Bills from a blocked supplier cannot be approved.</Text>
                  </View>
                  <Switch value={draft.blocked} onValueChange={(v) => setDraft((d) => (d ? { ...d, blocked: v } : d))} />
                </View>

                <TouchableOpacity style={[styles.button, styles.primary, saving && { opacity: 0.6 }]} onPress={save} disabled={saving}>
                  {saving ? <ActivityIndicator color="#FFF" /> : <Text style={styles.primaryText}>Save</Text>}
                </TouchableOpacity>
                {draft.id && (
                  <TouchableOpacity style={styles.deleteLink} onPress={remove}>
                    <Ionicons name="trash-outline" size={16} color="#DC2626" />
                    <Text style={{ color: '#DC2626', fontWeight: '600' }}>Remove from vendor list</Text>
                  </TouchableOpacity>
                )}
              </ScrollView>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F3F4F6' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 28 },
  topRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, paddingTop: 12, alignItems: 'center' },
  searchBox: {
    flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12,
    backgroundColor: '#FFF', borderRadius: 12, borderWidth: 1, borderColor: '#E5E7EB',
  },
  searchInput: { flex: 1, paddingVertical: 10, fontSize: 15, color: '#111827' },
  addButton: { width: 44, height: 44, borderRadius: 12, backgroundColor: '#4F46E5', justifyContent: 'center', alignItems: 'center' },
  errorBanner: { marginHorizontal: 20, marginTop: 10, padding: 10, borderRadius: 10, backgroundColor: '#FEF2F2' },
  errorText: { color: '#B91C1C' },
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#FFF', marginHorizontal: 20, marginTop: 12,
    padding: 14, borderRadius: 16, shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 5, elevation: 2,
  },
  avatar: { width: 42, height: 42, borderRadius: 21, backgroundColor: '#EEF2FF', justifyContent: 'center', alignItems: 'center' },
  name: { fontSize: 16, fontWeight: '600', color: '#1F2937' },
  sub: { fontSize: 12, color: '#9CA3AF', marginTop: 2 },
  emptyTitle: { color: '#6B7280', marginTop: 10, fontSize: 16, fontWeight: '600' },
  emptyText: { color: '#9CA3AF', marginTop: 8, fontSize: 14, textAlign: 'center', lineHeight: 20 },
  modalWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: {
    backgroundColor: '#FFF', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, maxHeight: '90%',
    paddingBottom: Platform.OS === 'ios' ? 36 : 20,
  },
  sheetTitle: { fontSize: 20, fontWeight: '800', color: '#111827' },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  label: { fontSize: 12, color: '#6B7280', fontWeight: '600', marginBottom: 4 },
  input: {
    borderWidth: 1, borderColor: '#E5E7EB', borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8,
    fontSize: 15, color: '#111827', backgroundColor: '#FAFAFA',
  },
  button: { justifyContent: 'center', alignItems: 'center', paddingVertical: 14, borderRadius: 12, marginTop: 20 },
  primary: { backgroundColor: '#4F46E5' },
  primaryText: { color: '#FFF', fontWeight: '700', fontSize: 16 },
  deleteLink: { flexDirection: 'row', gap: 6, alignItems: 'center', justifyContent: 'center', marginTop: 18, marginBottom: 6 },
});
