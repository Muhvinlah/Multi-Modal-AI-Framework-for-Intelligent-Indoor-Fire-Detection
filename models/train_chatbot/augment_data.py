import json
import random

input_file = r"./dataset.jsonl"
output_file = r"./dataset_100k.jsonl"
root_output_file = r"./dataset.jsonl"

with open(input_file, 'r', encoding='utf-8') as f:
    base_data = [json.loads(line) for line in f if line.strip()]

question_templates = [
    "{q}",
    "Tolong jelaskan {q_lower}",
    "Bisa beritahu saya {q_lower}",
    "Saya ingin bertanya: {q}",
    "Mohon info, {q_lower}",
    "Apakah Anda tahu {q_lower}",
    "Bisa bantu jawab: {q}",
    "Tanya dong, {q_lower}",
    "Halo Asisten, {q_lower}",
    "Bagaimana penjelasannya untuk: {q}",
    "Permisi, {q_lower}",
    "Pertanyaan: {q}",
    "{q}",
    "Bisa jelaskan detail tentang {q_lower}",
    "Admin, {q_lower}",
    "Tolong bantu saya dengan: {q}",
    "Ada info mengenai {q_lower}",
    "Bisa share informasi tentang {q_lower}",
    "Saya butuh info tentang: {q}",
    "Tolong berikan penjelasan mengenai {q_lower}",
    "Hai, bisa jelaskan {q_lower}",
    "Pertanyaan K3: {q}",
    "Mohon pencerahan tentang {q_lower}",
    "Jelaskan padaku {q_lower}",
    "Tolong deskripsikan {q_lower}",
    "Ada yang bisa beritahu {q_lower}",
    "Mohon bantuannya: {q}",
    "Permisi admin, {q_lower}",
    "Saya mau tanya tentang {q_lower}",
    "Gimana ya penjelasan untuk {q_lower}",
    "Beri tahu saya dong, {q_lower}",
    "Hi chatbot, {q_lower}",
    "Bro, {q_lower}",
    "Tolong pencerahannya, {q_lower}",
    "Share info dong ttg {q_lower}",
    "Mau nanya {q_lower}"
]

question_suffixes = [
    "",
    "",
    "",
    " Terima kasih.",
    " Thanks!",
    " Mohon secepatnya.",
    " Makasih min.",
    " Trims.",
    " Tolong dijawab ya.",
    " Penjelasan singkat aja.",
    " Mohon infonya ya.",
    " Bantu jawab min."
]

response_prefixes = [
    "",
    "",
    "Tentu! ",
    "Baik, ",
    "Tentu saja. ",
    "Berikut penjelasannya:\n",
    "Ini adalah informasi yang Anda butuhkan:\n",
    "Halo! ",
    "Tentu, saya bisa bantu. ",
    "Baiklah, ",
    "Menurut pedoman informasi: ",
    "Berikut adalah detailnya: ",
    "Menjawab pertanyaan Anda: ",
    "Berdasarkan standar K3, ",
    "Ini penjelasannya: ",
    "Tentu, berikut yang perlu Anda ketahui: ",
    "Baik, ini dia penjelasannya:\n",
    "Saya akan coba bantu jawab. ",
    "Sesuai dengan ketentuan standar, ",
    "Berikut informasi lengkapnya:\n",
    "Ini ya informasinya:\n",
    "Oke, ini penjelasannya:\n"
]

response_suffixes = [
    "",
    "",
    "",
    " Semoga bermanfaat!",
    " Semoga informasi ini mencerahkan ya.",
    "\n\nSilakan jika ada yang ingin ditanyakan lagi.",
    "\n\nHati-hati selalu dan utamakan keselamatan!",
    " Salam K3!",
    " Stay safe ya!",
    "\nJika butuh prosedur lain, sampaikan saja.",
    " Selalu utamakan keselamatan kerja ya!"
]

augmented_data = []
target_size = 100000

# Keep the original data intact first
for item in base_data:
    if item not in augmented_data:
        augmented_data.append(item)

visited_pairs = set()
for item in augmented_data:
    visited_pairs.add((item['instruction'], item['response']))

attempts = 0
max_attempts = target_size * 10

# Generate new data until we hit exactly 100,000
while len(augmented_data) < target_size and attempts < max_attempts:
    attempts += 1
    item = random.choice(base_data)
    q = item['instruction']
    r = item['response']
    
    q_lower = q[0].lower() + q[1:] if len(q) > 0 else q
    clean_q_lower = q_lower.rstrip('?')
    
    template = random.choice(question_templates)
    
    if "{" in template:
        if "{q_lower}" in template:
            if "?" in template and clean_q_lower != q_lower:
                new_q = template.format(q_lower=clean_q_lower)
            else:
                new_q = template.format(q_lower=q_lower)
        else:
            new_q = template.format(q=q)
    else:
        new_q = template
            
    q_suffix = random.choice(question_suffixes)
    # Cleanup before adding suffix
    clean_new_q = new_q.replace("??", "?").replace("? Mohon", " Mohon").replace("?.", "?")
    if not clean_new_q.endswith('?') and not clean_new_q.endswith('.'):
        clean_new_q += "?"
    if q_suffix:
        clean_new_q += q_suffix
        
    prefix = random.choice(response_prefixes)
    suffix = random.choice(response_suffixes)
    new_r = prefix + r + suffix
    
    if (clean_new_q, new_r) not in visited_pairs:
        visited_pairs.add((clean_new_q, new_r))
        augmented_data.append({"instruction": clean_new_q, "response": new_r})
        
    # show progress occasionally for script running
    if len(augmented_data) % 10000 == 0 and len(augmented_data) > (len(augmented_data)-1): # simplistic ping
        pass

if len(augmented_data) < target_size:
    print(f"Hanya mencapai {len(augmented_data)} data unik. Kombinasi maksimal sudah tercapai.")
    target_size = len(augmented_data)

random.shuffle(augmented_data)

# Write to both locations
for out_f in [output_file, root_output_file]:
    with open(out_f, 'w', encoding='utf-8') as f:
        for item in augmented_data[:target_size]:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

print(f"Generated EXACTLY {target_size} items into {output_file} and {root_output_file}")
