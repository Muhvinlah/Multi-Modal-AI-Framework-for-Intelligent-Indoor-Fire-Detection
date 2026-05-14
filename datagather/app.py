import tkinter as tk
from tkinter import ttk
import threading
import csv
import os
from datetime import datetime
from flask import Flask, request, jsonify
import logging

# Matikkan log Flask yang spam ke terminal
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

server = Flask(__name__)

# Shared state antara Flask dan Tkinter
sensor_data = {
    "mq4": 0, "mq5": 0, "mq135": 0, "mq2": 0, "mq7": 0, "mq3": 0
}
app_instance = None

@server.route('/', defaults={'path': ''}, methods=['POST', 'GET'])
@server.route('/<path:path>', methods=['POST', 'GET'])
def catch_all(path):
    if request.method == 'POST':
        if request.is_json:
            data = request.json
            sensor_data['mq4'] = data.get('mq4', 0)
            sensor_data['mq5'] = data.get('mq5', 0)
            sensor_data['mq135'] = data.get('mq135', 0)
            sensor_data['mq2'] = data.get('mq2', 0)
            sensor_data['mq7'] = data.get('mq7', 0)
            sensor_data['mq3'] = data.get('mq3', 0)
            
            # Beri tahu UI bahwa ada data baru
            if app_instance:
                app_instance.on_data_received()
                
            return jsonify({"status": "ok"})
    return "Server Data Gatherer Berjalan."

class DataGatherApp:
    def __init__(self, root):
        global app_instance
        app_instance = self
        self.root = root
        self.root.title("Dataset Gatherer - Sensor MQ ESP32")
        self.root.geometry("450x550")
        
        self.csv_file = "dataset_sensor.csv"
        self.auto_record = tk.BooleanVar(value=False)
        self.target_label = tk.StringVar(value="Udara Bersih (Aman)")
        
        self.init_csv()
        self.create_widgets()

    def init_csv(self):
        # Buat file CSV beserta headernya jika belum ada
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "mq4", "mq5", "mq135", "mq2", "mq7", "mq3", "target"])

    def create_widgets(self):
        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 11))
        style.configure("Header.TLabel", font=("Arial", 14, "bold"))
        style.configure("Value.TLabel", font=("Arial", 14, "bold"), foreground="blue")
        
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Real-time Sensor Data (RAW ADC)", style="Header.TLabel").pack(pady=(0, 10))
        
        # --- Frame Nilai Sensor ---
        self.val_vars = {}
        sensors_frame = ttk.LabelFrame(main_frame, text="Nilai Sensor ESP32", padding="10")
        sensors_frame.pack(fill=tk.X, pady=5)
        
        sensors = [
            ("MQ-4 (Metana/CNG)", "mq4"),
            ("MQ-5 (LPG)", "mq5"),
            ("MQ-135 (Air Quality)", "mq135"),
            ("MQ-2 (Smoke/Gas)", "mq2"),
            ("MQ-7 (CO)", "mq7"),
            ("MQ-3 (Alkohol)", "mq3"),
        ]
        
        for i, (label_text, key) in enumerate(sensors):
            ttk.Label(sensors_frame, text=f"{label_text}:").grid(row=i, column=0, sticky=tk.W, pady=3, padx=5)
            var = tk.StringVar(value="0")
            self.val_vars[key] = var
            ttk.Label(sensors_frame, textvariable=var, style="Value.TLabel").grid(row=i, column=1, sticky=tk.E, pady=3, padx=20)
            
        # --- Frame Label Target ---
        target_frame = ttk.LabelFrame(main_frame, text="Pilih Target / Kondisi Aktual Saat Ini", padding="10")
        target_frame.pack(fill=tk.X, pady=15)
        
        targets = [
            "Clean", 
            "Smoke", 
            "Gasoline",
            "Mixture"
        ]
        for t in targets:
            ttk.Radiobutton(target_frame, text=t, value=t, variable=self.target_label).pack(anchor=tk.W, pady=3)
            
        # --- Control Frame ---
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill=tk.X, pady=5)
        
        ttk.Checkbutton(ctrl_frame, text="Auto-Record (Simpan otomatis tiap data masuk)", variable=self.auto_record).pack(side=tk.LEFT)
        
        ttk.Button(main_frame, text="Manual Save Data", command=self.save_current_data).pack(fill=tk.X, pady=10)
        
        self.status_var = tk.StringVar(value="Menunggu data masuk (Port 8080)...")
        ttk.Label(main_frame, textvariable=self.status_var, foreground="gray").pack(side=tk.BOTTOM, pady=10)

    def on_data_received(self):
        # Cek apakah ada sensor yang bernilai 0 (kabel terputus) atau 4095 (korslet/maksimum ADC)
        is_faulty = False
        for k in ["mq4", "mq5", "mq135", "mq2", "mq7", "mq3"]:
            val = sensor_data[k]
            if val <= 0:
                is_faulty = True
                break

        # Jalankan pembaruan UI di thread utama
        self.root.after(0, self.update_ui, is_faulty)
        
        # Jika auto record nyala, proses penyimpanan
        if self.auto_record.get():
            if is_faulty:
                # Matikan auto record jika sensor faulty
                self.root.after(0, self.pause_recording_due_to_fault)
            else:
                self.root.after(0, self.save_current_data)

    def pause_recording_due_to_fault(self):
        self.auto_record.set(False)
        self.status_var.set("Auto-Record DIHENTIKAN: Terdeteksi sensor faulty (0 / 4095)")
        # Tambahkan visual warna merah untuk memperingati user
        self.root.config(bg="#ffcccc")
        self.root.after(2000, lambda: self.root.config(bg="SystemButtonFace"))

    def update_ui(self, is_faulty=False):
        self.val_vars["mq4"].set(str(sensor_data["mq4"]))
        self.val_vars["mq5"].set(str(sensor_data["mq5"]))
        self.val_vars["mq135"].set(str(sensor_data["mq135"]))
        self.val_vars["mq2"].set(str(sensor_data["mq2"]))
        self.val_vars["mq7"].set(str(sensor_data["mq7"]))
        self.val_vars["mq3"].set(str(sensor_data["mq3"]))
        
        if not is_faulty and "DIHENTIKAN" not in self.status_var.get():
            self.status_var.set(f"Last update: {datetime.now().strftime('%H:%M:%S')}")

    def save_current_data(self):
        timestamp = datetime.now().isoformat()
        target = self.target_label.get()
        
        row = [
            timestamp,
            sensor_data["mq4"],
            sensor_data["mq5"],
            sensor_data["mq135"],
            sensor_data["mq2"],
            sensor_data["mq7"],
            sensor_data["mq3"],
            target
        ]
        
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)
            
        # Tampilkan status berhasil
        self.status_var.set(f"Data tersimpan ({target}) pada {datetime.now().strftime('%H:%M:%S')}")

def run_gui():
    root = tk.Tk()
    app = DataGatherApp(root)
    root.mainloop()

if __name__ == '__main__':
    # Jalankan server Flask di background thread (Port 8080)
    server_thread = threading.Thread(target=lambda: server.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False))
    server_thread.daemon = True
    server_thread.start()
    
    # Jalankan GUI Tkinter
    run_gui()
