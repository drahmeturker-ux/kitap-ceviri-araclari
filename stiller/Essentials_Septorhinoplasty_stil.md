# Stil dosyası — Essentials of Septorhinoplasty: Philosophy, Approaches, Techniques (TR)

## Genel
- Mod: orta mod, orijinal sayfa düzeni, tıbbi çeviri modu. Kitap PDF'i 273 sayfa; Bölüm 1 = PDF s. 15–68 (s. 15 bölüm açılış/içindekiler sayfası, s. 65–67 kaynakça).
- PDF s. 1–14'te çıkarılabilir metin yok; kitapta kısaltma listesi ve dizin yok → kısaltmalar bölüm bölüm taranır.
- Üslup: resmi, akademik; yazarın birinci çoğul sesi korunur ("deneyimimiz", "öneririz").
- Düzen: Thieme iki sütun; çift sayfalarda içerik 14,2 pt sağa kaymış (extract2.py / layout2.py bunu hesaba katar).

## Kısaltmalar (kaynaktaki gibi kalır; bölümde ilk geçişte Türkçe açılım + kısaltma parantezde)
- OSA = obstrüktif uyku apnesi; SDB = uykuda solunum bozukluğu; AHI = apne-hipopne indeksi; AI = apne indeksi
- CPAP = sürekli pozitif hava yolu basıncı; nCPAP = nazal CPAP (nazal sürekli pozitif hava yolu basıncı)
- ESS = Epworth Uykululuk Ölçeği; EBM = kanıta dayalı tıp; BMI = vücut kitle indeksi; ODI = oksijen desatürasyon indeksi
- CT = bilgisayarlı tomografi; CSF = beyin omurilik sıvısı; FESS = fonksiyonel endoskopik sinüs cerrahisi
- SMAS = yüzeyel muskuloaponörotik sistem; PDS = polidioksanon sütür materyali; Nd:YAG lazer aynen
- RBH ölçeği (roughness, breathiness, hoarseness → pürüzlülük, nefeslilik, ses kısıklığı); BC → "MÖ" değil: "600 BC" → "MÖ 600" (BC kısaltma sayılmaz, Türkçe tarih yazımı); HNO (Almanca kurum adı içinde) aynen.
- Roma rakamları (II, III) aynen.

## Sayılar ve birimler
- Ondalık ayırıcı virgül (0.2 → 0,2); binlik ayırıcı nokta (1,000 → 1.000). Aralıklar en dash: 10–15 W.
- Sayı ile birim arasında boşluk korunur; birimler (mm, W, mbar, cm H2O) aynen.
- p değerleri: "(p < 0.01)" → "(p < 0,01)"; p italik kalır.

## Atıflar ve kaynaklar
- Üst simge atıflar (<sup>12,13</sup>) aynen, ilgili sözcük/cümlenin hemen arkasında.
- "et al" → "ve ark."; cümle içinde "X and Y" yazar adlarında "ve".
- Kaynakça girdileri çevrilmez; yalnızca başlık "References" → "Kaynaklar".
- Yazar satırı (Hans Behrbohm) aynen.

## Şekil/kutu/başlık kuralları
- "Fig. 1.2" → "Şekil 1.2"; "(see Fig. 1.9)" → "(bkz. Şekil 1.9)"; "(continued)" → "(devam)".
- Kalın şekil atıfları (**Fig. 1.1**) → (**Şekil 1.1**). Panel harfleri (a), (A) aynen.
- Kitap başlığı "Essentials of Septorhinoplasty" (kurs adı) aynen.
- Bölüm başlığı: Bölüm 1 = "Burun Cerrahisinin İkili Karakteri".

## İlk geçiş parantezi
- Önemli teknik terimlerin bölümdeki ilk geçişinde İngilizce terim parantezde: "semer burun (saddle nose)". Sonra tekrar edilmez.
- Yeni/belirsiz terimler: her bölümde ilk geçişte İngilizce parantezde; sözlükte notes = "uncertain".

## Kaynak hataları
- Bariz hata: düzeltilmiş biçim + [kaynakta: …]. Doz/sayı/klinik ifade asla yargıyla değiştirilmez.

## Kullanım günlüğü
- 2026-11-12: başlangıç oturum %20, haftalık 0–25%; Bölüm 1 (PDF s. 15–68, 50 sayfa metin + 3 sayfa kaynakça) çevrildi; 4 alt ajan (~410k token) + ana oturum (~250k token) ≈ 0,65M token. Sonraki: Bölüm 2 (PDF s. 69–94).

- 2026-11-12 (aynı oturum): Bölüm 2 (PDF s. 69–94; s. 93 karışık gövde+kaynakça, s. 94 kaynakça) çevrildi; 2 alt ajan (~200k token) + ana oturum (~120k) ≈ 0,32M token. Sonraki: Bölüm 3 (PDF s. 95–104).

## Bölüm 1'de bulunan kaynak hataları ([kaynakta: …] notlu)
- Berhard → Bernhard (von Langenbeck); Weissensse → Weissensee; "suspected between three points" → asılı (suspended); implatology → implantoloji; "Media Nasal Wall" → Medial; "sective broken" → selektif olarak; "columella bas" → taban; "protection" → projeksiyon (bağlam); Addson-Brown → Adson-Brown; batton → batten; ikinci "anosmia" → koku agnozisi (olfaktör agnozi).
- Kaynakta kalan, düzeltilmeyen: Jacques Joseph "graduated in Leipzig in 1861" (1865 doğumlu; muhtemelen 1890) — çeviride 1861 bırakıldı, kullanıcıya bildirildi.

## Bölüm 2 notları
- Bölüm 2 başlığı: "Çağdaş Rinoplasti: Kişisel İlkeler ve Felsefe".
- Crus çoğulu her yerde "kruslar" (krura değil); sıfat "krural".
- Kaynak notları: muculoaponeurotic → musculoaponeurotic; "cephalic margin of the lateral" → lateral krus; mortis → mortise; micro-osteotomies → mikroosteotomlar (alet).

## Teknik notlar
- extract2.py: Gulliver 6–7,5 pt = kaynakça girdisi ('ref'), gövde sayfalarında da karakter karakter aynen çizilir (karışık sayfalar için). Ligatür bölünmeleri ("super fi cial") ve küçük harf kerning bölünmeleri ("r hinoplasty") temizlenir.
- extract2.py: x_tolerance=1 bazı kelimeleri böler ("techniqu e", "f orceps", "2 3-year-old", "camou fl age"); satır sonu tirelerinde bileşik kelimeler birleşir ("sideto-side"). Çevirmen bunları kaynak hatası saymamalı.
- layout2.py: gövde DejaVu Serif Condensed 8,7 pt, Türkçe hece bölme (yumuşak tire), başlık/altyazı Carlito; kaynakça sayfaları karakter karakter yeniden çizilir, yalnız "References" → "Kaynaklar".
