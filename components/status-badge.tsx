import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

export function StatusBadge({ bill }: { bill: { status: string; error_count: number; issue_count: number; auto_approved?: boolean } }) {
  let label = 'Ready to approve';
  let color = '#2563EB';
  let bg = '#EFF6FF';
  if (bill.status === 'approved') {
    label = bill.auto_approved ? 'Auto-approved' : 'Approved';
    color = '#059669';
    bg = '#ECFDF5';
  } else if (bill.error_count > 0) {
    label = `Needs fixing · ${bill.error_count}`;
    color = '#DC2626';
    bg = '#FEF2F2';
  } else if (bill.issue_count > 0) {
    label = `Check · ${bill.issue_count}`;
    color = '#D97706';
    bg = '#FFFBEB';
  }
  return (
    <View style={[styles.badge, { backgroundColor: bg }]}>
      <Text style={[styles.badgeText, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 999 },
  badgeText: { fontSize: 12, fontWeight: '700' },
});
