# ClamAV Tarama Aracı

Windows'ta seçtiğiniz bir dosya veya klasör için [ClamAV](https://www.clamav.net/) taraması başlatan basit bir Python masaüstü arayüzü.

> Bu proje ClamAV motorunu içermez. Tarama yapabilmek için ClamAV'ı ayrıca kurmanız ve imza veritabanını güncel tutmanız gerekir.

## Özellikler

- Dosya veya klasör seçerek tarama başlatma
- ClamAV imza veritabanını `freshclam` ile güncelleme
- Tarama çıktısını ve tespit edilen tehditleri uygulama içinde gösterme
- ClamAV program yollarını otomatik bulma veya elle seçme
- Python standart kütüphanesindeki Tkinter arayüzünü kullanma; ek Python paketi gerektirmez

## Gereksinimler

- Windows 10 veya Windows 11
- Python 3.10 veya üzeri ve Tkinter
- [ClamAV for Windows](https://www.clamav.net/downloads)
- Güncel ClamAV imza veritabanı

## Kurulum ve çalıştırma

1. ClamAV'ın resmi Windows sürümünü indirip kurun.
2. Bu depoyu klonlayın veya ZIP olarak indirip açın.
3. Depo klasöründe PowerShell açıp uygulamayı çalıştırın:

   ```powershell
   python app.py
   ```

   `python` komutu yoksa Windows Python Launcher'ı deneyin:

   ```powershell
   py app.py
   ```

4. `clamscan.exe` ve `freshclam.exe` yollarını kontrol edin. Uygulama bulamazsa ClamAV kurulum klasöründeki dosyaları **Gözat** düğmesiyle seçin.
5. **İmzaları güncelle** düğmesine basın.
6. Taranacak dosya veya klasörü seçip **Taramayı başlat** düğmesine basın.

ClamAV kurulumu `freshclam` yapılandırması istiyorsa [resmi kurulum belgelerini](https://docs.clamav.net/manual/Installing.html) izleyin. İmza güncelleme komutlarının kullanımı [ClamAV imza belgelerinde](https://docs.clamav.net/manual/Usage/SignatureManagement.html) açıklanmıştır.

## Tarama sonuçları

ClamAV'ın çıkış kodları uygulamada özetlenir: `0` tespit yok, `1` tehdit bulundu, `2` tarama hatası. Ayrıntılı motor çıktısı uygulamanın **Tarama çıktısı** alanında görünür. Güncel imza veritabanı olmadan sonuçlara güvenmeyin.

## Güvenlik ve sınırlamalar

Bu uygulama yalnızca isteğe bağlı tarama arayüzüdür; gerçek zamanlı koruma sağlamaz, ClamAV motorunu dağıtmaz ve tüm zararlı yazılımları tespit etmeyi garanti etmez. Profesyonel güvenlik yazılımlarının yerine geçmez. Tarama sırasında şüpheli dosyaları açmayın veya çalıştırmayın.

## Geliştirme

Uygulama Python standart kütüphanesini kullanır. Harici Python bağımlılığı olmadığı için `pip install` adımı yoktur.

## Lisans

MIT. Ayrıntılar için [LICENSE](LICENSE) dosyasına bakın.
