import os
import io
import re
from flask import Flask, request, jsonify, send_file
from google.cloud import documentai
import firebase_admin

from firebase_admin import credentials, firestore, storage, auth 
import pandas as pd
import uuid # To generate unique filenames

# --- CONFIGURATION ---
PROJECT_ID = "smart-bill"
LOCATION = "us" 
PROCESSOR_ID = "PROCESSOR ID"

# --- FIREBASE CONFIG ---
SERVICE_ACCOUNT_FILE = "credentials.json"

# UPDATED: This is Storage Bucket ID 
STORAGE_BUCKET = "Storage Bucket ID"

try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
    firebase_admin.initialize_app(cred, {
        'storageBucket': STORAGE_BUCKET
    })
    db = firestore.client()
    bucket = storage.bucket() # Initialize Storage Bucket
    print("Successfully connected to Firebase Firestore & Storage.")
except Exception as e:
    print(f"Error connecting to Firebase: {e}")

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app = Flask(__name__)

# --- 1. DOCUMENT AI EXTRACTION LOGIC ---
def process_bill_with_document_ai(image_path: str):
    opts = {"api_endpoint": f"{LOCATION}-documentai.googleapis.com"}
    client = documentai.DocumentProcessorServiceClient.from_service_account_file(
        SERVICE_ACCOUNT_FILE, client_options=opts
    )
    name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

    with open(image_path, "rb") as image:
        image_content = image.read()

    document = documentai.RawDocument(content=image_content, mime_type="image/jpeg")
    request = documentai.ProcessRequest(name=name, raw_document=document)
    result = client.process_document(request=request)
    doc = result.document
    
    file_name = os.path.basename(image_path)
    extracted_data = {"File_Name": file_name, "line_items": []}
    
    def get_text(entity):
        response = ""
        if entity.text_anchor.text_segments:
            for segment in entity.text_anchor.text_segments:
                start_index = segment.start_index
                end_index = segment.end_index
                response += doc.text[start_index:end_index]
        elif entity.mention_text:
            response = entity.mention_text
        return response.strip().replace("\n", " ")

    for entity in doc.entities:
        entity_type = entity.type_
        if entity_type == "line_item":
            descriptions = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/description"]
            quantities = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/quantity"]
            rates = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/unit_price"]
            amounts = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/amount"]
            hsns = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/product_code"]
            discounts = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/discount"]
            cgsts = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/cgst"]
            sgsts = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/sgst"]
            gsts = [get_text(prop) for prop in entity.properties if prop.type_ == "line_item/gst"]

            num_items_in_group = len(descriptions)
            for i in range(num_items_in_group):
                item = {
                    "Item/Product Name": descriptions[i] if i < len(descriptions) else None,
                    "HSN/SAC": hsns[i] if i < len(hsns) else None,
                    "Quantity": quantities[i] if i < len(quantities) else None,
                    "Rate": rates[i] if i < len(rates) else None,
                    "CGST %": cgsts[i] if i < len(cgsts) else None, 
                    "SGST %": sgsts[i] if i < len(sgsts) else None, 
                    "Discount %": discounts[i] if i < len(discounts) else None,
                    "Amount": amounts[i] if i < len(amounts) else None
                }
                
                if not item["CGST %"] and not item["SGST %"] and i < len(gsts):
                    try:
                        gst_val = gsts[i].strip().replace('%', '')
                        total_gst = float(gst_val)
                        half_gst = total_gst / 2
                        item["CGST %"] = str(half_gst)
                        item["SGST %"] = str(half_gst)
                    except (ValueError, TypeError):
                        item["CGST %"] = gsts[i]
                
                extracted_data["line_items"].append(item)
        else:
            extracted_data[entity_type] = get_text(entity)

    return extracted_data

# --- 2. AUTH HELPER ---
def get_user_id_from_token(request):
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header: return None
        id_token = auth_header.split(' ').pop()
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token['uid']
    except Exception as e:
        print(f"Error verifying token: {e}")
        return None

# --- 3. SCAN BILL ENDPOINT ---
@app.route('/scan-bill', methods=['POST'])
def scan_bill_endpoint():
    user_id = get_user_id_from_token(request)
    if not user_id:
        return jsonify({"error": "Invalid or missing authentication token"}), 401

    if 'image' not in request.files:
        return jsonify({"error": "No image part"}), 400
    
    file = request.files['image']
    if file:
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        try:
            # 1. Upload Image to Firebase Storage (Cloud)
            blob_name = f"bills/{user_id}/{uuid.uuid4()}.jpg"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(filepath)
            # Make it public so the app can see it
            blob.make_public()
            image_url = blob.public_url
            
            print(f"Image uploaded to Cloud: {image_url}")

            # 2. Process with AI
            print("Processing with Document AI...")
            extracted_data = process_bill_with_document_ai(filepath)
            
            # Add the image URL
            extracted_data["image_url"] = image_url
            
            # Validation
            key_fields_found = 0
            if extracted_data.get("total_amount"): key_fields_found += 1
            if extracted_data.get("supplier_name"): key_fields_found += 1
            if extracted_data.get("line_items"): key_fields_found += 1
            if extracted_data.get("supplier_gst_number"): key_fields_found += 1

            if key_fields_found < 2:
                return jsonify({"message": "This doesn't look like a bill."}), 400

            # 3. Save to Firestore
            # We create a copy of the data to save to Firestore, adding the timestamp there.
            # This keeps 'extracted_data' clean (JSON serializable) for the return statement.
            firestore_data = extracted_data.copy()
            firestore_data["timestamp"] = firestore.SERVER_TIMESTAMP
            
            db.collection('users').document(user_id).collection('bills').add(firestore_data)
            print(f"Saved bill for user: {user_id}")

            return jsonify({
                "status": "success",
                "message": "Bill processed and saved to your account.",
                "data": extracted_data
            }), 200
        except Exception as e:
            print(f"An error occurred: {e}")
            return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "No image selected"}), 400

# --- 4. EXPORT BILLS ENDPOINT ---
@app.route('/export-bills', methods=['GET'])
def export_bills_endpoint():
    user_id = get_user_id_from_token(request)
    if not user_id:
        return jsonify({"error": "Invalid or missing authentication token"}), 401

    try:
        print(f"Fetching bills for user {user_id}...")
        bills_ref = db.collection('users').document(user_id).collection('bills').stream()
        
        # Group bills by supplier (Sheet Name)
        bills_by_sheet = {}

        def get_val(data, key):
            return data.get(key, "")

        for bill in bills_ref:
            data = bill.to_dict()
            
            # Logic to determine sheet name
            supplier_gst = data.get("supplier_gst_number", "").strip()
            supplier_name = data.get("supplier_name", "").strip()
            
            if supplier_name and supplier_gst:
                sheet_title = f"{supplier_name}_{supplier_gst}"
            elif supplier_gst:
                sheet_title = supplier_gst
            elif supplier_name:
                sheet_title = supplier_name
            else:
                sheet_title = "Unknown Supplier"

            # Sanitize sheet title
            safe_title = sheet_title[:31].replace(":", "").replace("\\", "").replace("/", "").replace("?", "").replace("*", "").replace("[", "").replace("]", "")
            
            if safe_title not in bills_by_sheet:
                bills_by_sheet[safe_title] = []
            
            bills_by_sheet[safe_title].append(data)

        if not bills_by_sheet:
            return jsonify({"message": "You have no bills to export."}), 404

        # --- CREATE MULTI-SHEET EXCEL FILE ---
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            
            # Loop through each group (Supplier)
            for sheet_name, bills in bills_by_sheet.items():
                sheet_rows = []
                
                # Loop through bills for this supplier
                for data in bills:
                    # 1. Header Block
                    sheet_rows.append([]) 
                    sheet_rows.append(["--- NEW BILL START ---", "File:", get_val(data, "File_Name")])
                    sheet_rows.append(["Supplier Name:", get_val(data, "supplier_name")])
                    sheet_rows.append(["Supplier Address:", get_val(data, "supplier_address")])
                    sheet_rows.append(["Supplier GST:", get_val(data, "supplier_gst_number")])
                    sheet_rows.append(["Supplier Phone:", get_val(data, "supplier_phone")])
                    sheet_rows.append(["Supplier Email:", get_val(data, "supplier_email")])
                    sheet_rows.append(["Invoice ID:", get_val(data, "invoice_id")])
                    sheet_rows.append(["Invoice Date:", get_val(data, "invoice_date")])
                    # Add Image Link to Excel
                    sheet_rows.append(["Bill Image:", get_val(data, "image_url")]) 
                    sheet_rows.append([]) 
                    
                    # 2. Product Table Header
                    sheet_rows.append(["S No.", "Item/Product Name", "HSN/SAC", "Quantity", "Rate", "CGST %", "SGST %", "Discount %", "Amount"])
                    
                    # 3. Product Rows
                    line_items = data.get("line_items", [])
                    if not line_items:
                        sheet_rows.append(["No line items found.", "", "", "", "", "", "", "", ""])
                    else:
                        for i, item in enumerate(line_items, 1):
                            row = [
                                i,
                                item.get("Item/Product Name", ""),
                                item.get("HSN/SAC", ""),
                                item.get("Quantity", ""),
                                item.get("Rate", ""),
                                item.get("CGST %", ""), 
                                item.get("SGST %", ""), 
                                item.get("Discount %", ""),
                                item.get("Amount", "")
                            ]
                            sheet_rows.append(row)
                    
                    sheet_rows.append([]) 
                    
                    # 4. Totals Block
                    sheet_rows.append(["", "", "", "", "", "", "", "Subtotal:", get_val(data, "sub_total")])
                    sheet_rows.append(["", "", "", "", "", "", "", "Total CGST:", get_val(data, "cgst_amount")])
                    sheet_rows.append(["", "", "", "", "", "", "", "Total SGST:", get_val(data, "sgst_amount")])
                    sheet_rows.append(["", "", "", "", "", "", "", "Total GST:", get_val(data, "total_gst_amount")])
                    sheet_rows.append(["", "", "", "", "", "", "", "TOTAL AMOUNT:", get_val(data, "total_amount")])
                    sheet_rows.append(["--- END OF BILL ---"])
                    sheet_rows.append([]) 

                # Write this supplier's bills to their own sheet
                df = pd.DataFrame(sheet_rows)
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
        
        output.seek(0)

        print(f"Successfully created Multi-Sheet Excel file for user {user_id}.")
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='SmartBill_Report.xlsx'
        )

    except Exception as e:
        print(f"Error exporting bills: {e}")
        return jsonify({"message": "An error occurred while exporting your data."}), 500

# --- NEW: Endpoint to get History & Stats ---
@app.route('/get-history', methods=['GET'])
def get_history():
    user_id = get_user_id_from_token(request)
    if not user_id: return jsonify({"error": "Unauthorized"}), 401

    try:
        bills_ref = db.collection('users').document(user_id).collection('bills').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
        
        history = []
        for bill in bills_ref:
            data = bill.to_dict()
            # Clean up data for frontend
            history.append({
                "id": bill.id,
                "supplier": data.get("supplier_name", "Unknown"),
                "date": data.get("invoice_date", "Unknown Date"),
                "total": data.get("total_amount", 0),
                "image": data.get("image_url", ""),
                "items_count": len(data.get("line_items", []))
            })
            
        return jsonify({"history": history}), 200
    except Exception as e:
         return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)