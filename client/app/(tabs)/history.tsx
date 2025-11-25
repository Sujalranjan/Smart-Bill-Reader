import { Ionicons } from '@expo/vector-icons';
import auth from '@react-native-firebase/auth';
import React, { useEffect, useState } from 'react';
import { Alert, FlatList, Image, RefreshControl, StyleSheet, Text, View } from 'react-native';

// --- NEW IMPORT ---
import { API_URL } from '../../constants/Config';

export default function HistoryScreen() {
  const [bills, setBills] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  const fetchBills = async () => {
    setRefreshing(true);
    const user = auth().currentUser;
    
    if (!user) {
      setRefreshing(false);
      return;
    }

    try {
      const token = await user.getIdToken();
      const response = await fetch(`${API_URL}/get-history`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error(`Server Error: ${response.status}`);
      }

      const json = await response.json();
      if (json.history) {
        setBills(json.history);
      }
    } catch (e) { 
      console.error(e);
      Alert.alert("Error", "Could not load history. Check your server connection.");
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => { 
    fetchBills(); 
  }, []);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Transaction History</Text>
      </View>
      
      {bills.length === 0 ? (
        <View style={styles.emptyState}>
          <Ionicons name="receipt-outline" size={64} color="#D1D5DB" />
          <Text style={styles.emptyText}>No bills scanned yet</Text>
        </View>
      ) : (
        <FlatList
          data={bills}
          keyExtractor={(item: any) => item.id}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={fetchBills} />}
          contentContainerStyle={{ paddingBottom: 20 }}
          renderItem={({ item }) => (
            <View style={styles.card}>
              {item.image ? (
                <Image source={{ uri: item.image }} style={styles.image} />
              ) : (
                <View style={[styles.image, { backgroundColor: '#E5E7EB' }]} />
              )}
              <View style={styles.info}>
                <Text style={styles.supplier} numberOfLines={1}>{item.supplier}</Text>
                <Text style={styles.date}>{item.date}</Text>
              </View>
              <View style={styles.amountContainer}>
                <Text style={styles.amount}>₹{item.total}</Text>
                <Text style={styles.items}>{item.items_count} items</Text>
              </View>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F3F4F6' },
  header: { padding: 20, paddingTop: 60, backgroundColor: '#FFF' },
  headerTitle: { fontSize: 24, fontWeight: '800', color: '#111827' },
  card: {
    flexDirection: 'row',
    backgroundColor: '#FFF',
    marginHorizontal: 20,
    marginTop: 12,
    padding: 12,
    borderRadius: 16,
    alignItems: 'center',
    shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 5, elevation: 2
  },
  image: { width: 50, height: 50, borderRadius: 12, marginRight: 12 },
  info: { flex: 1 },
  supplier: { fontSize: 16, fontWeight: '600', color: '#1F2937' },
  date: { fontSize: 12, color: '#9CA3AF', marginTop: 2 },
  amountContainer: { alignItems: 'flex-end' },
  amount: { fontSize: 16, fontWeight: '700', color: '#059669' },
  items: { fontSize: 12, color: '#9CA3AF' },
  emptyState: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  emptyText: { color: '#9CA3AF', marginTop: 10, fontSize: 16 },
});