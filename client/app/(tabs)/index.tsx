import { Ionicons } from '@expo/vector-icons';
import { getAuth } from '@react-native-firebase/auth';
import * as FileSystem from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import * as Sharing from 'expo-sharing';
import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View
} from 'react-native';

// --- IMPORT API URL FROM CONFIG ---
import { API_URL } from '../../constants/Config';

const auth = getAuth();
const { StorageAccessFramework } = FileSystem; // Required for "Save to Device" on Android

export default function ScanScreen() { 
  const [isLoading, setIsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("Processing Bill...");

  useEffect(() => {
    (async () => {
      if (Platform.OS !== 'web') {
        await ImagePicker.requestMediaLibraryPermissionsAsync();
        await ImagePicker.requestCameraPermissionsAsync();
      }
    })();
  }, []);

  const uploadImage = async (imageUri: string) => {
    setIsLoading(true);
    setLoadingText("Uploading & Analyzing...");

    const user = auth.currentUser;
    if (!user) { Alert.alert("Error", "Not logged in"); setIsLoading(false); return; }
    const idToken = await user.getIdToken();

    const formData = new FormData();
    let uriParts = imageUri.split('.');
    let fileType = uriParts[uriParts.length - 1];
    formData.append('image', { uri: imageUri, type: `image/${fileType}`, name: `bill.${fileType}` } as any);

    try {
      const response = await fetch(`${API_URL}/scan-bill`, {
        method: 'POST',
        body: formData,
        headers: { 'Content-Type': 'multipart/form-data', 'Authorization': `Bearer ${idToken}` },
      });
      const json = await response.json();
      if (response.ok) Alert.alert('Success!', json.message);
      else Alert.alert('Error', json.message);
    } catch (e) { Alert.alert('Upload Failed', 'Check server URL in Config.ts'); } 
    finally { setIsLoading(false); }
  };

  const openGallery = async () => {
    let res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, quality: 1 });
    if (!res.canceled) uploadImage(res.assets[0].uri);
  };
  
  const openCamera = async () => {
    let res = await ImagePicker.launchCameraAsync({ allowsEditing: true, quality: 1 });
    if (!res.canceled) uploadImage(res.assets[0].uri);
  };

  // --- DOWNLOAD HELPER ---
  const fetchExcelBlob = async () => {
    const user = auth.currentUser;
    if (!user) { Alert.alert("Error", "Not logged in."); return null; }
    const idToken = await user.getIdToken();

    try {
      const response = await fetch(`${API_URL}/export-bills`, {
        method: 'GET',
        headers: { 'Authorization': `Bearer ${idToken}` },
      });

      if (!response.ok) {
        Alert.alert("Export Failed", "Server returned an error.");
        return null;
      }
      return await response.blob();
    } catch (e) {
      console.error(e);
      return null;
    }
  };

  // --- ACTION 1: SHARE REPORT ---
  const handleShareReport = async () => {
    setIsLoading(true);
    setLoadingText("Preparing Share...");
    try {
        const blob = await fetchExcelBlob();
        if (!blob) { setIsLoading(false); return; }

        const date = new Date();
        const filename = `SmartBill_${date.getTime()}.xlsx`;
        const fileUri = `${FileSystem.documentDirectory}${filename}`;

        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = async () => {
            const base64data = (reader.result as string).split(',')[1];
            await FileSystem.writeAsStringAsync(fileUri, base64data, { encoding: FileSystem.EncodingType.Base64 });
            
            if (await Sharing.isAvailableAsync()) {
                await Sharing.shareAsync(fileUri, {
                    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    dialogTitle: 'Share Report',
                    UTI: 'com.microsoft.excel.xlsx'
                });
            }
            setIsLoading(false);
        };
    } catch (e) { setIsLoading(false); }
  };

  // --- ACTION 2: SAVE TO DEVICE (RESTORED) ---
  const handleDownloadReport = async () => {
    setIsLoading(true);
    setLoadingText("Saving...");
    
    try {
        const blob = await fetchExcelBlob();
        if (!blob) { 
            Alert.alert("Error", "Could not download file.");
            setIsLoading(false); 
            return; 
        }

        const date = new Date();
        const filename = `SmartBill_Report_${date.getFullYear()}-${date.getMonth()+1}-${date.getDate()}.xlsx`;

        // --- ANDROID SAVE LOGIC (StorageAccessFramework) ---
        if (Platform.OS === 'android') {
            const permissions = await StorageAccessFramework.requestDirectoryPermissionsAsync();
            if (permissions.granted) {
                const reader = new FileReader();
                reader.readAsDataURL(blob);
                reader.onloadend = async () => {
                    const base64data = (reader.result as string).split(',')[1];
                    try {
                        const uri = await StorageAccessFramework.createFileAsync(permissions.directoryUri, filename, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
                        await FileSystem.writeAsStringAsync(uri, base64data, { encoding: FileSystem.EncodingType.Base64 });
                        Alert.alert("Saved!", `File saved to selected folder.`);
                    } catch (e) {
                        Alert.alert("Error", "Could not save file.");
                    }
                    setIsLoading(false);
                };
            } else {
                setIsLoading(false);
            }
        } else {
            // --- iOS SAVE LOGIC (Share to Files) ---
            const fileUri = `${FileSystem.documentDirectory}${filename}`;
            const reader = new FileReader();
            reader.readAsDataURL(blob);
            reader.onloadend = async () => {
                const base64data = (reader.result as string).split(',')[1];
                await FileSystem.writeAsStringAsync(fileUri, base64data, { encoding: FileSystem.EncodingType.Base64 });
                await Sharing.shareAsync(fileUri);
                setIsLoading(false);
            };
        }

    } catch (e) {
        console.error(e);
        Alert.alert("Error", "Failed to download.");
        setIsLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.greeting}>Hello, Data Analyst! </Text>
        <Text style={styles.subtitle}>What would you like to do?</Text>
      </View>

      <ScrollView contentContainerStyle={styles.cardContainer} showsVerticalScrollIndicator={false}>
        {isLoading ? (
          <View style={styles.loaderCard}>
            <ActivityIndicator size="large" color="#4F46E5" />
            <Text style={styles.loaderText}>{loadingText}</Text>
          </View>
        ) : (
          <>
            <TouchableOpacity style={[styles.card, styles.cardPrimary]} onPress={openCamera}>
              <View style={styles.iconCircle}>
                <Ionicons name="camera" size={32} color="#4F46E5" />
              </View>
              <View>
                <Text style={styles.cardTitle}>Scan New Bill</Text>
                <Text style={styles.cardSub}>Use camera to capture</Text>
              </View>
            </TouchableOpacity>

            <TouchableOpacity style={styles.card} onPress={openGallery}>
              <View style={[styles.iconCircle, { backgroundColor: '#ECFDF5' }]}>
                <Ionicons name="images" size={32} color="#10B981" />
              </View>
              <View>
                <Text style={styles.cardTitle}>Upload Image</Text>
                <Text style={styles.cardSub}>Select from gallery</Text>
              </View>
            </TouchableOpacity>

            <TouchableOpacity style={styles.card} onPress={handleShareReport}>
              <View style={[styles.iconCircle, { backgroundColor: '#FFFBEB' }]}>
                <Ionicons name="share-social" size={32} color="#F59E0B" />
              </View>
              <View>
                <Text style={styles.cardTitle}>Share Report</Text>
                <Text style={styles.cardSub}>WhatsApp, Email, Drive</Text>
              </View>
            </TouchableOpacity>

            {/* RESTORED DOWNLOAD BUTTON */}
            <TouchableOpacity style={styles.card} onPress={handleDownloadReport}>
              <View style={[styles.iconCircle, { backgroundColor: '#EFF6FF' }]}>
                <Ionicons name="download" size={32} color="#2563EB" />
              </View>
              <View>
                <Text style={styles.cardTitle}>Save to Device</Text>
                <Text style={styles.cardSub}>Download Excel File</Text>
              </View>
            </TouchableOpacity>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F3F4F6', paddingTop: 60, paddingHorizontal: 20 },
  header: { marginBottom: 20 },
  greeting: { fontSize: 28, fontWeight: '800', color: '#111827' },
  subtitle: { fontSize: 16, color: '#6B7280', marginTop: 5 },
  cardContainer: { gap: 16, paddingBottom: 40 },
  card: { backgroundColor: '#FFFFFF', padding: 20, borderRadius: 20, flexDirection: 'row', alignItems: 'center', gap: 16, shadowColor: '#000', shadowOpacity: 0.05, shadowRadius: 10, elevation: 2 },
  cardPrimary: { borderWidth: 1, borderColor: '#E0E7FF' },
  iconCircle: { width: 60, height: 60, borderRadius: 30, backgroundColor: '#EEF2FF', justifyContent: 'center', alignItems: 'center' },
  cardTitle: { fontSize: 18, fontWeight: '700', color: '#1F2937' },
  cardSub: { fontSize: 14, color: '#9CA3AF' },
  loaderCard: { backgroundColor: '#FFFFFF', padding: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  loaderText: { marginTop: 16, fontSize: 16, color: '#4F46E5', fontWeight: '600' },
});