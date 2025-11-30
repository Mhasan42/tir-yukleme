import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import uuid
from collections import Counter
import io

# Kütüphane Kontrolü
try:
    from py3dbp import Packer, Bin, Item
except ImportError:
    st.error("Lütfen terminale şu komutu yazın: pip install py3dbp")
    st.stop()

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Lojistik Pro Mobil", layout="wide", initial_sidebar_state="expanded")

# Mobil için CSS İyileştirmesi
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; }
    div[data-testid="metric-container"] { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🚛 Mobil Tır Yükleme Asistanı")
st.caption("Optimum Sıkıştırma Modu (v7.1)")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Tır Ayarları")
    t_en = st.number_input("En (cm)", value=245)
    t_boy = st.number_input("Boy (cm)", value=1360)
    t_yuk = st.number_input("Yükseklik", value=270)
    kapak_payi = st.number_input("Kapak Payı (cm)", value=30)
    max_kg = st.number_input("Max Tonaj (kg)", value=26000)
    
    st.markdown("---")
    st.header("🔄 Yön Ayarları")
    dikey_izin = st.checkbox("Ürünler Dik Çevrilebilir mi?", value=True, help="İşaretli ise ürünleri yan veya dik çevirerek sığdırmayı dener.")

    net_boy = t_boy - kapak_payi
    tir_hacim_m3 = (t_en * net_boy * t_yuk) / 1_000_000
    if tir_hacim_m3 > 0:
        st.success(f"🚛 NET KAPASİTE: {tir_hacim_m3:.2f} m³")

# --- ÜRÜN GİRİŞİ ---
if 'cargo' not in st.session_state:
    st.session_state.cargo = []

# Mobilde daha iyi görünmesi için sekmeli yapı
tab_giris, tab_simulasyon = st.tabs(["📝 Ürün Girişi", "🚚 Yükleme Planı"])

with tab_giris:
    st.subheader("Set Tanımla")
    col_set1, col_set2 = st.columns([2, 1])
    set_ad = col_set1.text_input("Set Adı", "Gold Set")
    adet = col_set2.number_input("Adet", 1, 1000, 60)
    
    with st.expander("📦 Ölçüler ve Renkler (Tıkla Aç)", expanded=True):
        # Baza
        st.markdown("**Baza**")
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        b_en = c1.number_input("En", 90, key="b_en"); b_boy = c2.number_input("Boy", 190, key="b_boy"); b_yuk = c3.number_input("Yük", 28, key="b_yuk")
        b_color = c4.color_picker("Renk", "#8B4513", key="b_c")
        
        # Başlık
        st.markdown("**Başlık**")
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        h_en = c1.number_input("En", 90, key="h_en"); h_boy = c2.number_input("Boy", 100, key="h_boy"); h_yuk = c3.number_input("Yük", 10, key="h_yuk")
        h_color = c4.color_picker("Renk", "#FFD700", key="h_c")
        
        # Yatak
        st.markdown("**Yatak**")
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        y_en = c1.number_input("En", 90, key="y_en"); y_boy = c2.number_input("Boy", 190, key="y_boy"); y_yuk = c3.number_input("Yük", 25, key="y_yuk")
        y_color = c4.color_picker("Renk", "#ADD8E6", key="y_c")

    if st.button("Listeye Ekle (+)", type="primary"):
        grup_id = str(uuid.uuid4())[:8]
        for i in range(adet):
            tid = f"{grup_id}_{i}"
            st.session_state.cargo.append({"ad": set_ad, "tip": "Baza", "en": b_en, "boy": b_boy, "yuk": b_yuk, "kg": 40, "tid": tid, "lb": 100, "color": b_color, "orig_dim": (b_en, b_boy, b_yuk)})
            st.session_state.cargo.append({"ad": set_ad, "tip": "Başlık", "en": h_en, "boy": h_boy, "yuk": h_yuk, "kg": 15, "tid": tid, "lb": 100, "color": h_color, "orig_dim": (h_en, h_boy, h_yuk)})
            st.session_state.cargo.append({"ad": set_ad, "tip": "Yatak", "en": y_en, "boy": y_boy, "yuk": y_yuk, "kg": 20, "tid": tid, "lb": 0, "color": y_color, "orig_dim": (y_en, y_boy, y_yuk)})
        st.success(f"{adet} takım eklendi.")

    if len(st.session_state.cargo) > 0:
        if st.button("Listeyi Temizle 🗑️"):
            st.session_state.cargo = []
            st.rerun()
        
        # Özet Tablo
        df = pd.DataFrame(st.session_state.cargo)
        st.dataframe(df.groupby(['ad', 'tip']).size().reset_index(name='Talep'), use_container_width=True)

# --- FONKSİYON: PACKER ---
def run_packer(items_to_pack, bin_dims, rotasyon_izni):
    packer = Packer()
    packer.add_bin(Bin('Tir', bin_dims[0], bin_dims[1], bin_dims[2], bin_dims[3]))
    
    item_map = {}
    for item in items_to_pack:
        unique_id = f"{item['tid']}|{item['tip']}|{uuid.uuid4()}"
        item_map[unique_id] = item
        # rotation=True/False ayarı py3dbp kütüphanesinin güncel sürümlerinde desteklenir
        # Desteklemiyorsa boyutları manuel değiştirmek gerekir, burada standart kullanıyoruz.
        p = Item(unique_id, float(item['en']), float(item['boy']), float(item['yuk']), float(item['kg']))
        p.loadbear = item['lb']
        packer.add_item(p)
    
    # number_of_decimals: Hassasiyet
    packer.pack(bigger_first=True, distribute_items=False, number_of_decimals=0)
    return packer, item_map

# --- SİMÜLASYON ---
with tab_simulasyon:
    if len(st.session_state.cargo) == 0:
        st.info("Lütfen önce 'Ürün Girişi' sekmesinden ürün ekleyin.")
    else:
        st.subheader("Yükleme Simülasyonu")
        
        if st.button("HESAPLA VE SIKIŞTIR 🚀", type="primary"):
            
            prog_bar = st.progress(0, text="Analiz ediliyor...")
            
            # 1. TEST YÜKLEMESİ
            bin_dims = (float(t_en), float(net_boy), float(t_yuk), float(max_kg))
            packer_test, _ = run_packer(st.session_state.cargo, bin_dims, dikey_izin)
            
            if not packer_test.bins:
                st.error("Ürünler sığmadı!")
                st.stop()

            # 2. SET ANALİZİ
            b_test = packer_test.bins[0]
            set_counter = Counter([item.name.split('|')[0] for item in b_test.items])
            tam_sigan_idler = {sid for sid, count in set_counter.items() if count == 3}
            sigan_set_sayisi = len(tam_sigan_idler)
            
            prog_bar.progress(50, text=f"{sigan_set_sayisi} set sığdı. Boşluklar alınıyor...")
            
            # 3. SIKIŞTIRMA (RE-PACK)
            optimize_liste = [i for i in st.session_state.cargo if i['tid'] in tam_sigan_idler]
            packer_final, item_map_final = run_packer(optimize_liste, bin_dims, dikey_izin)
            b_final = packer_final.bins[0]
            
            prog_bar.progress(100, text="Tamamlandı.")

            # 4. GÖRSELLEŞTİRME
            fig = go.Figure()
            
            # Tır
            x_len, y_len, z_len = bin_dims[0], bin_dims[1], bin_dims[2]
            lines_x = [0, x_len, x_len, 0, 0, 0, x_len, x_len, 0, 0, 0, 0, x_len, x_len, x_len, x_len]
            lines_y = [0, 0, y_len, y_len, 0, 0, 0, y_len, y_len, 0, 0, 0, 0, y_len, y_len, 0]
            lines_z = [0, 0, 0, 0, 0, z_len, z_len, z_len, z_len, z_len, 0, z_len, z_len, 0, z_len, 0]
            fig.add_trace(go.Scatter3d(x=lines_x, y=lines_y, z=lines_z, mode='lines', line=dict(color='black', width=3), name='Tır', hoverinfo='none'))
            
            # Kapak Payı
            fig.add_trace(go.Mesh3d(x=[0, x_len, x_len, 0, 0, x_len, x_len, 0], y=[y_len, y_len, y_len+kapak_payi, y_len+kapak_payi, y_len, y_len, y_len+kapak_payi, y_len+kapak_payi], z=[0, 0, 0, 0, z_len, z_len, z_len, z_len], color='red', opacity=0.1, name='Kapak Payı'))

            dolu_hacim = 0
            csv_data = [] # Rapor için veri
            
            for item in b_final.items:
                orig = item_map_final[item.name]
                x, y, z = [float(k) for k in item.position]
                w, h, d = [float(k) for k in item.get_dimension()]
                dolu_hacim += (w*h*d)

                # Yön
                orig_h = float(orig['orig_dim'][2])
                durus = "YATAY" if abs(d - orig_h) < 1.0 else "DİK"
                
                # Rapor Verisi
                csv_data.append({
                    "Set ID": orig['tid'].split('_')[1],
                    "Parça": orig['tip'],
                    "Durum": durus,
                    "Konum (X,Y,Z)": f"{x:.0f}, {y:.0f}, {z:.0f}",
                    "Boyut (E,B,Y)": f"{w:.0f}x{h:.0f}x{d:.0f}"
                })

                # Kutu Çiz
                fig.add_trace(go.Mesh3d(x=[x, x+w, x+w, x, x, x+w, x+w, x], y=[y, y, y+h, y+h, y, y, y+h, y+h], z=[z, z, z, z, z+d, z+d, z+d, z+d], i=[7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2], j=[3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3], k=[0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6], color=orig['color'], opacity=1, flatshading=True, name=orig['tip'], hovertext=f"{orig['tip']}<br>{durus}", hoverinfo='text'))
                
                # Wireframe
                wx = [x, x+w, x+w, x, x, x+w, x+w, x, x, x+w, x+w, x, x, x, x+w, x+w]
                wy = [y, y, y+h, y+h, y, y, y+h, y+h, y, y, y, y, y+h, y+h, y+h, y+h]
                wz = [z, z, z, z, z+d, z+d, z+d, z+d, z, z, z+d, z+d, z, z+d, z, z+d]
                fig.add_trace(go.Scatter3d(x=wx, y=wy, z=wz, mode='lines', line=dict(color='black', width=2), showlegend=False, hoverinfo='none'))

            fig.update_layout(scene=dict(aspectmode='data', xaxis_title='En', yaxis_title='Boy', zaxis_title='Yükseklik'), margin=dict(l=0,r=0,b=0,t=0), height=500)
            st.plotly_chart(fig, use_container_width=True)

            # METRİKLER
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("✅ Tam Set", f"{sigan_set_sayisi}")
            c2.metric("❌ Dışarıda", f"{len({i['tid'] for i in st.session_state.cargo}) - sigan_set_sayisi}")
            doluluk = ((dolu_hacim/1e6) / tir_hacim_m3) * 100
            c3.metric("Doluluk", f"%{doluluk:.1f}")

            # --- RAPOR İNDİRME ---
            if csv_data:
                df_rapor = pd.DataFrame(csv_data)
                csv = df_rapor.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📋 Yükleme Listesini İndir (Excel/CSV)",
                    data=csv,
                    file_name='yukleme_plani.csv',
                    mime='text/csv',
                    type='secondary'
                )