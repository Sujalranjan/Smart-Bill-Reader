import { Ionicons } from '@expo/vector-icons';
import auth from '@react-native-firebase/auth';
import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View
} from 'react-native';

// Use your config
import { API_URL } from '../../constants/Config';

export default function StatsScreen() {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState<any[]>([]);

  useEffect(() => {
    const unsubscribe = auth().onAuthStateChanged((user) => {
        if (user) fetchData(); else setLoading(false);
    });
    return unsubscribe;
  }, []);

  const fetchData = async () => {
    const user = auth().currentUser;
    if (!user) { setLoading(false); setRefreshing(false); return; }
    try {
      const token = await user.getIdToken();
      const res = await fetch(`${API_URL}/get-history`, { headers: { 'Authorization': `Bearer ${token}` } });
      const json = await res.json();
      if (json.history) setData(json.history);
    } catch (e) { Alert.alert("Error", "Analytics Unavailable"); } 
    finally { setLoading(false); setRefreshing(false); }
  };

  if (loading) return <View style={styles.center}><ActivityIndicator size="large" color="#4F46E5" /></View>;

  // --- CALCULATE STATS (FIXED LOGIC) ---
  let totalSpent = 0;
  const supplierSet = new Set(); 

  data.forEach(bill => {
    // 1. Get the raw value
    let amount = bill.total;

    // 2. If it's a string, remove commas (e.g. "1,200.50" -> "1200.50")
    if (typeof amount === 'string') {
        amount = amount.replace(/,/g, ''); 
    }

    // 3. Convert to float safely
    const val = parseFloat(amount) || 0;
    
    totalSpent += val;
    
    const sup = bill.supplier || "Unknown";
    supplierSet.add(sup);
  });

  const totalBills = data.length;
  const totalSuppliers = supplierSet.size;
  const avgBillValue = totalBills > 0 ? (totalSpent / totalBills).toFixed(0) : 0;

  return (
    <ScrollView 
      style={styles.container} 
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={fetchData} />}
    >
       <View style={styles.header}>
        <Text style={styles.headerTitle}>Dashboard</Text>
        <Text style={styles.headerSub}>Overview of your expenses</Text>
      </View>

      {/* KEY METRICS CARDS */}
      <View style={styles.grid}>
        
        {/* CARD 1: TOTAL SPENT */}
        <View style={[styles.card, styles.cardFullWidth, { backgroundColor: '#4F46E5' }]}>
            <View>
              <Text style={styles.cardLabelLight}>Total Expenditure</Text>
              <Text style={styles.cardValueLight}>₹{totalSpent.toLocaleString()}</Text>
            </View>
            <View style={[styles.iconCircle, { backgroundColor: 'rgba(255,255,255,0.2)' }]}>
              <Ionicons name="wallet" size={32} color="#FFF" />
            </View>
        </View>

        {/* CARD 2: TOTAL BILLS */}
        <View style={[styles.card, styles.cardHalf]}>
            <View style={[styles.iconCircle, { backgroundColor: '#ECFDF5' }]}>
                <Ionicons name="receipt" size={28} color="#10B981" />
            </View>
            <Text style={styles.cardValue}>{totalBills}</Text>
            <Text style={styles.cardLabel}>Total Bills</Text>
        </View>

        {/* CARD 3: TOTAL SUPPLIERS */}
        <View style={[styles.card, styles.cardHalf]}>
             <View style={[styles.iconCircle, { backgroundColor: '#EFF6FF' }]}>
                <Ionicons name="people" size={28} color="#2563EB" />
            </View>
            <Text style={styles.cardValue}>{totalSuppliers}</Text>
            <Text style={styles.cardLabel}>Suppliers</Text>
        </View>

        {/* CARD 4: AVERAGE BILL */}
        <View style={[styles.card, styles.cardFullWidth]}>
             <View style={{flexDirection:'row', alignItems:'center'}}>
                <View style={[styles.iconCircle, { backgroundColor: '#FFFBEB', marginRight: 15 }]}>
                    <Ionicons name="stats-chart" size={28} color="#F59E0B" />
                </View>
                <View>
                  <Text style={styles.cardValue}>₹{Number(avgBillValue).toLocaleString()}</Text>
                  <Text style={styles.cardLabel}>Average Bill Value</Text>
                </View>
             </View>
        </View>
      </View>

      {/* LIST HEADER */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Recent Activity</Text>
        <Ionicons name="arrow-down-circle-outline" size={20} color="#6B7280" />
      </View>

      {data.length === 0 && (
        <Text style={styles.empty}>No data available yet. Scan a bill!</Text>
      )}
      
      <View style={{height: 40}} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F3F4F6' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { padding: 20, paddingTop: 60, backgroundColor: '#FFF', borderBottomWidth: 1, borderBottomColor: '#E5E7EB' },
  headerTitle: { fontSize: 28, fontWeight: '800', color: '#111827' },
  headerSub: { fontSize: 14, color: '#6B7280', marginTop: 2 },
  
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 15,
    justifyContent: 'space-between',
  },
  card: {
    backgroundColor: '#FFF',
    padding: 20,
    borderRadius: 20,
    marginBottom: 15,
    shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 5, elevation: 2,
  },
  cardFullWidth: {
    width: '100%',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  cardHalf: {
    width: '48%', 
    alignItems: 'flex-start'
  },
  iconCircle: {
    width: 50, height: 50, borderRadius: 25,
    justifyContent: 'center', alignItems: 'center', marginBottom: 10
  },
  cardLabel: { fontSize: 14, color: '#6B7280', fontWeight: '600' },
  cardValue: { fontSize: 24, color: '#111827', fontWeight: '800', marginBottom: 4 },
  cardLabelLight: { fontSize: 14, color: '#E0E7FF', fontWeight: '600' },
  cardValueLight: { fontSize: 32, color: '#FFFFFF', fontWeight: '800' },
  sectionHeader: { 
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', 
    marginHorizontal: 20, marginTop: 10, marginBottom: 10 
  },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: '#374151' },
  empty: { textAlign: 'center', marginTop: 40, color: '#9CA3AF' }
});
