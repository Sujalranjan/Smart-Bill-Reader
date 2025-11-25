import { useColorScheme } from '@/hooks/use-color-scheme';
import { Ionicons } from '@expo/vector-icons'; // We use this for beautiful, cross-platform icons
import { getAuth, signOut } from '@react-native-firebase/auth';
import { Tabs, useRouter } from 'expo-router';
import React from 'react';
import { Platform, TouchableOpacity } from 'react-native';
import { Colors } from '../../constants/Colors';

const auth = getAuth();

export default function TabLayout() {
  const colorScheme = useColorScheme();
  const router = useRouter();

  const handleLogout = async () => {
    try {
      await signOut(auth);
      router.replace('/login');
    } catch (error) {
      console.error("Logout Error:", error);
    }
  };

  const activeTintColor = Colors[colorScheme ?? 'light']?.tint || '#2563EB';

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: activeTintColor,
        tabBarInactiveTintColor: '#9CA3AF', // A nice gray for inactive tabs
        headerShown: true,
        tabBarStyle: {
          height: Platform.OS === 'ios' ? 85 : 65, // Taller tabs look more modern
          paddingBottom: Platform.OS === 'ios' ? 30 : 10,
          paddingTop: 10,
          backgroundColor: '#FFFFFF',
          borderTopWidth: 0, // Remove the ugly line
          elevation: 10, // Add a soft shadow on Android
          shadowColor: '#000', // Add a soft shadow on iOS
          shadowOffset: { width: 0, height: -2 },
          shadowOpacity: 0.1,
          shadowRadius: 4,
        },
        headerStyle: {
          backgroundColor: '#81a038ff',
          shadowColor: 'transparent', // Remove header shadow for a cleaner look
          elevation: 0,
        },
        headerTitleStyle: {
          fontWeight: '800',
          fontSize: 20,
          color: '#1F2937',
        },
      }}>
      
      {/* 1. SCAN TAB */}
      <Tabs.Screen
        name="index"
        options={{
          title: 'Smart Bill',
          tabBarLabel: 'Scan',
          // Switch icon based on 'focused' state (Outline vs Filled)
          tabBarIcon: ({ color, focused }) => (
            <Ionicons 
              name={focused ? "scan-circle" : "scan-circle-outline"} 
              size={28} 
              color={color} 
            />
          ),
          headerRight: () => (
            <TouchableOpacity onPress={handleLogout} style={{ marginRight: 20 }}>
              <Ionicons 
                name="log-out-outline" 
                size={24} 
                color="#EF4444" // Red color for logout
              />
            </TouchableOpacity>
          ),
        }}
      />

      {/* 2. HISTORY TAB */}
      <Tabs.Screen
        name="history"
        options={{
          title: 'History',
          tabBarLabel: 'History',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons 
              name={focused ? "time" : "time-outline"} 
              size={28} 
              color={color} 
            />
          ),
        }}
      />
      
      {/* 3. ANALYTICS TAB */}
      <Tabs.Screen
        name="stats"
        options={{
          title: 'Analytics',
          tabBarLabel: 'Insights',
          tabBarIcon: ({ color, focused }) => (
            <Ionicons 
              name={focused ? "pie-chart" : "pie-chart-outline"} 
              size={28} 
              color={color} 
            />
          ),
        }}
      />
    </Tabs>
  );
}