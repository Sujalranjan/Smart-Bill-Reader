import { getAuth, GoogleAuthProvider, signInWithCredential } from '@react-native-firebase/auth';
import { GoogleSignin, GoogleSigninButton } from '@react-native-google-signin/google-signin';
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Dimensions,
  ImageBackground,
  StyleSheet,
  Text,
  View
} from 'react-native';

const auth = getAuth();
const { width } = Dimensions.get('window');

// ‼️ ENSURE WEB_CLIENT_ID IS HERE ‼️
const WEB_CLIENT_ID = '430558994471-nimt6lj5o4ajjh5sd83hrbha08bb1g6a.apps.googleusercontent.com';

try {
  GoogleSignin.configure({
    webClientId: WEB_CLIENT_ID,
  });
} catch (error) {
  console.error("GoogleSignin.configure ERROR:", error);
}

export default function LoginScreen() {
  const [isLoading, setIsLoading] = useState(false);

  async function onGoogleButtonPress() {
    setIsLoading(true);
    if (WEB_CLIENT_ID.includes('YOUR-WEB-CLIENT-ID')) {
      Alert.alert("Config Error", "Please update WEB_CLIENT_ID in app/login.tsx");
      setIsLoading(false);
      return;
    }

    try {
      await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
      const response = await GoogleSignin.signIn();
      if (response.type !== 'success') {
        // User closed the Google account picker
        setIsLoading(false);
        return;
      }
      const idToken = response.data.idToken;
      if (!idToken) throw new Error('Google did not return an ID token. Check the web client ID.');
      const googleCredential = GoogleAuthProvider.credential(idToken);
      await signInWithCredential(auth, googleCredential);
    } catch (error: any) {
      setIsLoading(false);
      let msg = "Login failed.";
      if (error.code === '12500') msg = "Sign-in cancelled or Google Play Services error.";
      else if (error.code === '10') msg = "Developer Error: Check SHA-1 keys.";
      else if (error.message) msg = error.message;
      Alert.alert("Login Error", msg);
    }
  }

  return (
    <ImageBackground
      source={{ uri: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop' }}
      style={styles.background}
    >
      <View style={styles.overlay}>
        <View style={styles.card}>
          <Text style={styles.emoji}>🧾</Text>
          <Text style={styles.title}>SmartBill</Text>
          <Text style={styles.subtitle}>AI-Powered Expense Tracking</Text>
          
          <View style={styles.divider} />

          {isLoading ? (
            <ActivityIndicator size="large" color="#4F46E5" />
          ) : (
            <View style={styles.buttonContainer}>
               <Text style={styles.signInText}>Sign in to continue</Text>
              <GoogleSigninButton
                style={styles.googleButton}
                size={GoogleSigninButton.Size.Wide}
                color={GoogleSigninButton.Color.Dark}
                onPress={onGoogleButtonPress}
              />
            </View>
          )}
        </View>
        <Text style={styles.footer}>Secure • Fast • Automated</Text>
      </View>
    </ImageBackground>
  );
}

const styles = StyleSheet.create({
  background: { flex: 1, justifyContent: 'center' },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(17, 24, 39, 0.75)', // Dark slate overlay
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  card: {
    width: '100%',
    maxWidth: 400,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    borderRadius: 24,
    paddingVertical: 40,
    paddingHorizontal: 30,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.25,
    shadowRadius: 20,
    elevation: 10,
  },
  emoji: { fontSize: 48, marginBottom: 10 },
  title: {
    fontSize: 36,
    fontWeight: '800',
    color: '#1F2937',
    letterSpacing: -1,
  },
  subtitle: {
    fontSize: 16,
    color: '#6B7280',
    marginTop: 5,
    fontWeight: '500',
  },
  divider: {
    height: 1,
    width: '100%',
    backgroundColor: '#E5E7EB',
    marginVertical: 30,
  },
  buttonContainer: { alignItems: 'center', width: '100%' },
  signInText: {
    fontSize: 14,
    color: '#6B7280',
    marginBottom: 15,
    fontWeight: '500',
  },
  googleButton: { width: '100%', height: 55 },
  footer: {
    position: 'absolute',
    bottom: 40,
    color: 'rgba(255,255,255,0.6)',
    fontSize: 13,
    fontWeight: '500',
  },
});