import auth, { FirebaseAuthTypes } from '@react-native-firebase/auth';
import { Stack, useRouter, useSegments } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

export default function AppLayout() {
  const [initializing, setInitializing] = useState(true);
  const [user, setUser] = useState<FirebaseAuthTypes.User | null>(null);
  const router = useRouter();
  const segments = useSegments();

  useEffect(() => {
    const unsubscribe = auth().onAuthStateChanged((u) => {
      setUser(u);
      setInitializing(false);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (initializing) return;
    const onLogin = segments[0] === 'login';
    if (user && onLogin) {
      router.replace('/(tabs)');
    } else if (!user && !onLogin) {
      router.replace('/login');
    }
  }, [user, initializing, segments]);

  if (initializing) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <Stack>
      <Stack.Screen name="login" options={{ headerShown: false }} />
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="bill/[id]" options={{ title: 'Review Bill', headerBackTitle: 'Back' }} />
    </Stack>
  );
}
