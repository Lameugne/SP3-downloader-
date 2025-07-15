#!/usr/bin/env python3
"""
Téléchargeur SP3 intelligent avec produits combinés GPS/GLONASS - VERSION MODIFIÉE
Modifications v2.2:
- Suppression du répertoire MGEX inexistant
- Correction nomenclature ultra-rapides
- Priorité aux intervalles : 01S > 30S > 05M > 15M
"""

import os
import sys
import json
import requests
import gzip
import logging
from datetime import datetime, timedelta
from pathlib import Path

def setup_logging():
    """Configure le logging"""
    if getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).parent
        log_file = app_dir / "sp3_downloader.log"
    else:
        log_file = Path(__file__).parent / "sp3_downloader.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

class ConfigManager:
    """Gestionnaire de configuration"""
    
    def __init__(self):
        if getattr(sys, 'frozen', False):
            # Mode exécutable
            self.config_dir = Path(sys.executable).parent
        else:
            # Mode développement
            self.config_dir = Path(__file__).parent
        
        self.config_file = self.config_dir / "sp3_config.json"
        self.default_config = {
            "jwt_token": (
                ),
            "output_directory": r"C:\1-Data\01-Projet\ProjetPY\Test_GNSS",
            "user_name": "Utilisateur",
            "auto_cleanup": True
        }
        
        self.config = self.load_config()
    
    def load_config(self):
        """Charge la configuration depuis le fichier"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # Vérifier que toutes les clés par défaut existent
                for key, value in self.default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            else:
                return self.default_config.copy()
        except Exception as e:
            logger.error(f"Erreur chargement config: {e}")
            return self.default_config.copy()
    
    def save_config(self):
        """Sauvegarde la configuration"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde config: {e}")
            return False
    
    def get(self, key):
        """Récupère une valeur de configuration"""
        return self.config.get(key, self.default_config.get(key))
    
    def set(self, key, value):
        """Définit une valeur de configuration"""
        self.config[key] = value

class SP3CombinedDownloader:
    """Téléchargeur SP3 intelligent pour produits combinés GPS/GLONASS avec configuration"""
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.output_dir = Path(self.config.get('output_directory'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Session avec authentification
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.config.get("jwt_token")}',
            'User-Agent': 'SP3-Combined-Downloader/2.2'
        })
        
        # URLs de base CDDIS (MGEX supprimé)
        self.cddis_base = "https://cddis.nasa.gov/archive/gnss/products"
        self.broadcast_base = "https://cddis.nasa.gov/archive/gnss/data/daily"
        
        # Seuils de disponibilité des produits IGS (en heures)
        self.availability_thresholds = {
            'final': 12 * 24,      # 12 jours minimum
            'rapid': 24,           # 1 jour minimum  
            'ultra_rapid': 3       # 3 heures minimum
        }
        
        # Intervalles de temps par ordre de priorité
        self.time_intervals = ['01S', '30S', '05M', '15M']
        
        # Précisions et caractéristiques des produits
        self.product_specs = {
            'final': {
                'precision': '2-3 cm',
                'description': 'Référence de précision maximale',
                'availability': '12 jours après',
                'priority': 1
            },
            'rapid': {
                'precision': '2,5 cm',
                'description': 'Solution quotidienne rapide',
                'availability': '1 jour après',
                'priority': 2
            },
            'ultra_rapid': {
                'precision': '3-5 cm',
                'description': 'Solution temps quasi-réel',
                'availability': '3 heures après',
                'priority': 3
            }
        }
    
    def update_config(self, config_manager):
        """Met à jour la configuration"""
        self.config = config_manager
        self.output_dir = Path(self.config.get('output_directory'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Mettre à jour l'authentification
        self.session.headers.update({
            'Authorization': f'Bearer {self.config.get("jwt_token")}'
        })
        
    def gps_epoch(self):
        """Époque GPS : 6 janvier 1980 00:00:00 UTC"""
        return datetime(1980, 1, 6, 0, 0, 0)
    
    def date_to_gps_week(self, date_str):
        """Convertit une date en semaine GPS et jour de la semaine"""
        if isinstance(date_str, str):
            if '/' in date_str:
                date = datetime.strptime(date_str, "%d/%m/%Y")
            else:
                date = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            date = date_str
        
        gps_start = self.gps_epoch()
        delta = date - gps_start
        gps_week = delta.days // 7
        day_of_week = delta.days % 7
        
        return gps_week, day_of_week, date
    
    def analyze_data_availability(self, target_date):
        """Analyse la disponibilité des produits"""
        if isinstance(target_date, str):
            if '/' in target_date:
                date_obj = datetime.strptime(target_date, "%d/%m/%Y")
            else:
                date_obj = datetime.strptime(target_date, "%Y-%m-%d")
        else:
            date_obj = target_date
        
        now = datetime.now()
        time_diff = now - date_obj
        hours_elapsed = time_diff.total_seconds() / 3600
        
        analysis = {
            'date_requested': date_obj,
            'hours_elapsed': hours_elapsed,
            'optimal_product': None,
            'data_unavailable': False
        }
        
        if hours_elapsed >= self.availability_thresholds['final']:
            analysis['optimal_product'] = 'final'
        elif hours_elapsed >= self.availability_thresholds['rapid']:
            analysis['optimal_product'] = 'rapid'
        elif hours_elapsed >= self.availability_thresholds['ultra_rapid']:
            analysis['optimal_product'] = 'ultra_rapid'
        else:
            analysis['data_unavailable'] = True
        
        return analysis
    
    def generate_combined_sp3_filenames(self, target_date, product_type):
        """
        Génère les noms de fichiers SP3 avec priorité aux intervalles de temps
        Version modifiée pour nomenclature ultra-rapides et intervalles prioritaires
        """
        gps_week, day_of_week, date_obj = self.date_to_gps_week(target_date)
        year = date_obj.year
        doy = date_obj.timetuple().tm_yday
        
        filenames = []
        
        # Déterminer le format selon la semaine GPS
        use_new_format = gps_week >= 2238  # Transition novembre 2022
        
        if use_new_format:
            # Format moderne (depuis GPS Week 2238)
            if product_type == 'final':
                # PRODUITS FINAUX avec intervalles prioritaires
                for interval in self.time_intervals:
                    filenames.append(f"IGS0OPSFIN_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    filenames.append(f"COD0MGXFIN_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    filenames.append(f"GFZ0MGXFIN_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    filenames.append(f"WUM0MGXFIN_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    
                    
            elif product_type == 'rapid':
                # PRODUITS RAPIDES avec intervalles prioritaires
                for interval in self.time_intervals:
                    filenames.append(f"IGS0OPSRAP_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    filenames.append(f"COD0OPSRAP_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    filenames.append(f"GFZ0OPSRAP_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    filenames.append(f"JPL0OPSRAP_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    filenames.append(f"IGR0OPSRAP_{year}{doy:03d}0000_01D_{interval}_ORB.SP3.gz")
                    
            elif product_type == 'ultra_rapid':
                # PRODUITS ULTRA-RAPIDES - Format corrigé
                now = datetime.now()
                
                # Les ultra-rapides IGS sont disponibles toutes les 6h: 00, 06, 12, 18 UTC
                available_hours = []
                
                if date_obj.date() == now.date():
                    # Date d'aujourd'hui - calculer les heures disponibles avec délai 3h
                    current_hour_utc = now.hour
                    for h in [18, 12, 6, 0]:  # Ordre décroissant (plus récent en premier)
                        if h <= current_hour_utc - 3:  # Délai de 3h
                            available_hours.append(f"{h:02d}")
                    
                    # Si aucune heure disponible aujourd'hui, essayer hier soir
                    if not available_hours:
                        yesterday = date_obj - timedelta(days=1)
                        _, _, yesterday_obj = self.date_to_gps_week(yesterday)
                        yesterday_doy = yesterday_obj.timetuple().tm_yday
                        for h in [18, 12]:  # Heures de fin de journée d'hier
                            for interval in self.time_intervals:
                                filenames.append(f"IGS0OPSULT_{year}{yesterday_doy:03d}{h:02d}00_02D_{interval}_ORB.SP3.gz")
                                filenames.append(f"COD0OPSULT_{year}{yesterday_doy:03d}{h:02d}00_02D_{interval}_ORB.SP3.gz")
                                filenames.append(f"GFZ0OPSULT_{year}{yesterday_doy:03d}{h:02d}00_02D_{interval}_ORB.SP3.gz")
                else:
                    # Date passée - toutes les heures disponibles
                    available_hours = ['18', '12', '06', '00']
                
                # Ajouter les heures disponibles avec intervalles prioritaires
                for hour in available_hours:
                    for interval in self.time_intervals:
                        # Format principal observé dans les exemples fournis
                        filenames.append(f"IGS0OPSULT_{year}{doy:03d}{hour}00_02D_{interval}_ORB.SP3.gz")
                        filenames.append(f"COD0OPSULT_{year}{doy:03d}{hour}00_02D_{interval}_ORB.SP3.gz")
                        filenames.append(f"GFZ0OPSULT_{year}{doy:03d}{hour}00_02D_{interval}_ORB.SP3.gz")
                        filenames.append(f"JPL0OPSULT_{year}{doy:03d}{hour}00_02D_{interval}_ORB.SP3.gz")
                        
                        # Variantes 1D (1 jour)
                        filenames.append(f"IGS0OPSULT_{year}{doy:03d}{hour}00_01D_{interval}_ORB.SP3.gz")
                        filenames.append(f"COD0OPSULT_{year}{doy:03d}{hour}00_01D_{interval}_ORB.SP3.gz")
                        filenames.append(f"GFZ0OPSULT_{year}{doy:03d}{hour}00_01D_{interval}_ORB.SP3.gz")
                
                # Format hérité comme fallback (sans priorité d'intervalles)
                legacy_hours = []
                if date_obj.date() == now.date():
                    current_hour = now.hour
                    for h in [21, 18, 15, 12, 9, 6, 3, 0]:  # Toutes les 3h
                        if h <= current_hour - 3:  # Avec délai de 3h
                            legacy_hours.append(h)
                    
                    # Si pas d'heures disponibles aujourd'hui, essayer hier
                    if not legacy_hours:
                        yesterday = date_obj - timedelta(days=1)
                        gps_week_y, day_of_week_y, _ = self.date_to_gps_week(yesterday)
                        for h in [21, 18, 15, 12]:  # Heures de fin de journée d'hier
                            filenames.append(f"igu{gps_week_y:04d}{day_of_week_y}_{h:02d}.sp3.Z")
                else:
                    # Date passée - toutes les heures disponibles (format ancien)
                    legacy_hours = [21, 18, 15, 12, 9, 6, 3, 0]
                
                # Ajouter les heures legacy
                for hour in legacy_hours:
                    filenames.append(f"igu{gps_week:04d}{day_of_week}_{hour:02d}.sp3.Z")
        
        else:
            # Format hérité (avant GPS Week 2238)
            if product_type == 'final':
                for center in ['cod', 'gfz', 'whu']:
                    filenames.append(f"{center}{gps_week:04d}{day_of_week}.sp3.Z")
                filenames.append(f"igs{gps_week:04d}{day_of_week}.sp3.Z")
                    
            elif product_type == 'rapid':
                # Format hérité pour rapides
                for center in ['cod', 'gfz', 'jpl']:
                    filenames.append(f"{center}r{gps_week:04d}{day_of_week}.sp3.Z")
                filenames.append(f"igr{gps_week:04d}{day_of_week}.sp3.Z")
                    
            elif product_type == 'ultra_rapid':
                # Format hérité pour ultra-rapides avec logique d'heures
                now = datetime.now()
                
                if date_obj.date() == now.date():
                    # Date d'aujourd'hui - heures disponibles avec délai
                    current_hour = now.hour
                    for hour in [21, 18, 15, 12, 9, 6, 3, 0]:
                        if hour <= current_hour - 3:  # Délai de 3h
                            filenames.append(f"igu{gps_week:04d}{day_of_week}_{hour:02d}.sp3.Z")
                    
                    # Si aucune heure disponible aujourd'hui, essayer hier
                    if len([f for f in filenames if 'igu' in f]) == 0:
                        yesterday = date_obj - timedelta(days=1)
                        gps_week_y, day_of_week_y, _ = self.date_to_gps_week(yesterday)
                        for hour in [21, 18]:
                            filenames.append(f"igu{gps_week_y:04d}{day_of_week_y}_{hour:02d}.sp3.Z")
                else:
                    # Date passée - toutes les heures
                    for hour in [21, 18, 15, 12, 9, 6, 3, 0]:
                        filenames.append(f"igu{gps_week:04d}{day_of_week}_{hour:02d}.sp3.Z")
                
                # Autres centres pour format hérité
                for hour in [18, 12, 6, 0]:
                    for center in ['cod', 'gfz']:
                        filenames.append(f"{center}u{gps_week:04d}{day_of_week}_{hour:02d}.sp3.Z")
        
        return filenames, gps_week, use_new_format
    
    def smart_download_sp3(self, target_date):
        """Téléchargement intelligent avec sélection automatique du produit optimal"""
        try:
            availability = self.analyze_data_availability(target_date)
            
            if availability['data_unavailable']:
                print(f"❌ Aucun produit disponible (minimum 3h requis)")
                return None
            
            optimal_product = availability['optimal_product']
            print(f"🔍 Téléchargement {optimal_product.upper()}...")
            
            result = self.download_product_type(target_date, optimal_product)
            if result:
                print(f"✅ Succès {optimal_product.upper()}")
                return result
            else:
                print(f"❌ Échec {optimal_product.upper()}")
                
                # LOGIQUE DE FALLBACK AUTOMATIQUE
                if optimal_product == 'ultra_rapid':
                    print(f"🔄 Fallback automatique vers RAPID...")
                    result = self.download_product_type(target_date, 'rapid')
                    if result:
                        print(f"✅ Succès RAPID (fallback)")
                        return result
                    
                    print(f"🔄 Fallback automatique vers FINAL...")
                    result = self.download_product_type(target_date, 'final')
                    if result:
                        print(f"✅ Succès FINAL (fallback)")
                        return result
                        
                elif optimal_product == 'rapid':
                    print(f"🔄 Fallback automatique vers FINAL...")
                    result = self.download_product_type(target_date, 'final')
                    if result:
                        print(f"✅ Succès FINAL (fallback)")
                        return result
                
                return None
            
        except Exception as e:
            logger.error(f"Erreur téléchargement: {str(e)}")
            return None
    
    def download_product_type(self, target_date, product_type):
        """Télécharge un type de produit spécifique"""
        try:
            filenames, gps_week, use_new_format = self.generate_combined_sp3_filenames(target_date, product_type)
            
            # Un seul répertoire maintenant (pas de MGEX)
            repository = f"{self.cddis_base}/{gps_week:04d}/"
            
            print(f"   Recherche de {len(filenames)} variantes de fichiers...")
            print(f"   📅 Semaine GPS: {gps_week}, Format: {'IGS20' if use_new_format else 'Hérité'}")
            print(f"   📂 Répertoire: {repository}")
            
            # Afficher la priorité des intervalles
            if product_type in ['final', 'rapid', 'ultra_rapid'] and use_new_format:
                print(f"   ⏱️  Priorité intervalles: {' > '.join(self.time_intervals)}")
            
            # Afficher quelques exemples de fichiers recherchés
            if len(filenames) > 0:
                print(f"   📋 Exemples recherchés:")
                for i, fname in enumerate(filenames[:5]):
                    print(f"      {i+1}. {fname}")
                if len(filenames) > 5:
                    print(f"      ... et {len(filenames)-5} autres variantes")
            
            # Recherche dans le répertoire unique
            for j, filename in enumerate(filenames):
                file_url = repository + filename
                
                try:
                    response = self.session.head(file_url, timeout=8)
                    
                    if response.status_code == 200:
                        # Extraire l'intervalle du nom de fichier pour l'affichage
                        interval_match = None
                        for interval in self.time_intervals:
                            if f"_{interval}_" in filename:
                                interval_match = interval
                                break
                        
                        if interval_match:
                            print(f"   ✅ Trouvé [{interval_match}]: {filename}")
                        else:
                            print(f"   ✅ Trouvé: {filename}")
                            
                        return self.download_file(file_url, filename)
                        
                    elif response.status_code == 404:
                        # Afficher seulement les premiers échecs pour diagnostic
                        if j < 1:
                            print(f"   🔄  .........  ")
                    elif response.status_code == 401:
                        print(f"   🔐 401 Authentification requise: {filename}")
                        print(f"   💡 Vérifiez votre token JWT dans les paramètres")
                        break
                    else:
                        if j < 3:
                            print(f"   ⚠️ Erreur {response.status_code}: {filename}")
                    
                except Exception as e:
                    if j < 3:
                        print(f"   ⚠️ Erreur réseau: {filename}")
                    continue
            
            print(f"   ❌ Aucun fichier {product_type} trouvé")
            return None
            
        except Exception as e:
            logger.error(f"Erreur download_product_type: {str(e)}")
            return None
    
    def download_file(self, file_url, filename):
        """Télécharge un fichier"""
        try:
            response = self.session.get(file_url, stream=True, timeout=120)
            response.raise_for_status()
            
            output_path = self.output_dir / filename
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Décompression automatique
            if filename.endswith('.gz'):
                return self.decompress_file(output_path)
            elif filename.endswith('.Z'):
                return self.decompress_unix_z(output_path)
            
            return str(output_path)
                    
        except Exception as e:
            logger.error(f"Erreur téléchargement {filename}: {str(e)}")
            return None
    
    def decompress_file(self, compressed_path):
        """Décompresse un fichier .gz avec gestion d'erreurs"""
        try:
            decompressed_path = compressed_path.with_suffix('')
            print(f"📦 Décompression gzip: {decompressed_path.name}")
            
            with gzip.open(compressed_path, 'rb') as f_in:
                with open(decompressed_path, 'wb') as f_out:
                    f_out.write(f_in.read())
            
            # Supprimer le fichier compressé pour économiser l'espace
            auto_cleanup = self.config.get('auto_cleanup')
            if auto_cleanup is None or auto_cleanup:  # Par défaut True
                compressed_path.unlink()
            
            size = decompressed_path.stat().st_size
            print(f"✅ Décompression réussie: {size:,} octets")
            return str(decompressed_path)
            
        except Exception as e:
            logger.error(f"Erreur décompression gzip: {str(e)}")
            print(f"❌ Erreur décompression: {str(e)}")
            return str(compressed_path)
    
    def decompress_unix_z(self, compressed_path):
        """Décompresse un fichier .Z (Unix compress)"""
        try:
            import subprocess
            decompressed_path = compressed_path.with_suffix('')
            print(f"📦 Décompression Unix .Z: {decompressed_path.name}")
            
            # Essayer la commande uncompress
            result = subprocess.run(['uncompress', str(compressed_path)], 
                                  capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and decompressed_path.exists():
                size = decompressed_path.stat().st_size
                print(f"✅ Décompression Unix réussie: {size:,} octets")
                return str(decompressed_path)
            else:
                print(f"⚠️ Décompression Unix échouée, fichier gardé compressé")
                return str(compressed_path)
                
        except Exception as e:
            logger.warning(f"Erreur décompression Unix: {str(e)}")
            print(f"⚠️ Fichier gardé compressé: {compressed_path}")
            return str(compressed_path)
    
    def analyze_sp3_file(self, file_path):
        """Analyse factuelle d'un fichier SP3"""
        try:
            print(f"\n📊 ANALYSE FICHIER SP3")
            print(f"📁 {Path(file_path).name}")
            
            # Vérifier que le fichier existe
            if not Path(file_path).exists():
                print(f"❌ Fichier non trouvé: {file_path}")
                return False
            
            # Vérifier que ce n'est pas un fichier compressé
            if file_path.endswith('.gz') or file_path.endswith('.Z'):
                print(f"❌ Fichier encore compressé - décompression a échoué")
                return False
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # Vérifier que le fichier n'est pas vide
            if not lines:
                print(f"❌ Fichier vide")
                return False
            
            satellites = {}
            constellations = set()
            all_satellites = set()
            
            for line in lines[:200]:
                if line.startswith('+'):
                    sat_section = line[9:].strip()
                    pos = 0
                    while pos < len(sat_section):
                        if pos + 2 < len(sat_section):
                            sat_id = sat_section[pos:pos+3]
                            if len(sat_id) == 3 and sat_id[0].isalpha() and sat_id[1:].isdigit():
                                constellation = sat_id[0].upper()
                                constellations.add(constellation)
                                all_satellites.add(sat_id)
                                if constellation not in satellites:
                                    satellites[constellation] = set()
                                satellites[constellation].add(sat_id)
                        pos += 3
            
            constellation_names = {
                'G': 'GPS', 'R': 'GLONASS', 'E': 'Galileo', 
                'C': 'BeiDou', 'J': 'QZSS', 'S': 'SBAS'
            }
            
            file_size = Path(file_path).stat().st_size
            total_satellites = len(all_satellites)
            
            print(f"💾 Taille: {file_size / (1024*1024):.2f} MB")
            print(f"🛰️ Satellites: {total_satellites}")
            print(f"🌐 Constellations: {len(constellations)}")
            
            if total_satellites == 0:
                print(f"⚠️ Aucun satellite détecté - vérifiez le format du fichier")
                # Afficher les premières lignes pour diagnostic
                print(f"📋 Premières lignes du fichier:")
                for i, line in enumerate(lines[:5]):
                    print(f"   {i+1}: {line.strip()}")
                return False
            
            for const_code in sorted(constellations):
                const_name = constellation_names.get(const_code, f'Constellation {const_code}')
                sat_count = len(satellites.get(const_code, []))
                print(f"   {const_name}: {sat_count}")
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur analyse: {str(e)}")
            logger.error(f"Erreur analyse SP3: {str(e)}")
            return False

def show_settings_menu(config_manager):
    """Affiche le menu des paramètres"""
    while True:
        print("\n" + "=" * 50)
        print("⚙️  MENU PARAMÈTRES")
        print("=" * 50)
        print(f"👤 Utilisateur: {config_manager.get('user_name')}")
        print(f"📁 Répertoire: {config_manager.get('output_directory')}")
        print(f"🔑 Token: {'●' * 20}...{config_manager.get('jwt_token')[-20:]}")
        print(f"🧹 Nettoyage auto: {'✅' if config_manager.get('auto_cleanup') else '❌'}")
        
        print(f"\n📋 OPTIONS:")
        print(f"1. Changer nom utilisateur")
        print(f"2. Changer répertoire de sortie")
        print(f"3. Changer token JWT")
        print(f"4. Activer/Désactiver nettoyage auto")
        print(f"5. Réinitialiser paramètres")
        print(f"6. Retour au menu principal")
        
        choice = input("\nChoix (1-6): ").strip()
        
        if choice == '1':
            name = input("Nouveau nom d'utilisateur: ").strip()
            if name:
                config_manager.set('user_name', name)
                config_manager.save_config()
                print(f"✅ Nom mis à jour: {name}")
        
        elif choice == '2':
            print(f"Répertoire actuel: {config_manager.get('output_directory')}")
            new_dir = input("Nouveau répertoire (ou Entrée pour annuler): ").strip()
            if new_dir:
                try:
                    test_path = Path(new_dir)
                    test_path.mkdir(parents=True, exist_ok=True)
                    # Test d'écriture
                    test_file = test_path / "test.tmp"
                    test_file.write_text("test")
                    test_file.unlink()
                    
                    config_manager.set('output_directory', str(test_path))
                    config_manager.save_config()
                    print(f"✅ Répertoire mis à jour: {test_path}")
                except Exception as e:
                    print(f"❌ Erreur: {e}")
        
        elif choice == '3':
            print(f"Token actuel: {config_manager.get('jwt_token')[:50]}...")
            print(f"⚠️  Attention: Le token JWT doit être valide pour NASA Earthdata")
            new_token = input("Nouveau token JWT (ou Entrée pour annuler): ").strip()
            if new_token:
                if len(new_token) > 100:  # Vérification basique
                    config_manager.set('jwt_token', new_token)
                    config_manager.save_config()
                    print(f"✅ Token mis à jour")
                else:
                    print(f"❌ Token trop court (doit faire >100 caractères)")
        
        elif choice == '4':
            current = config_manager.get('auto_cleanup')
            config_manager.set('auto_cleanup', not current)
            config_manager.save_config()
            status = "activé" if not current else "désactivé"
            print(f"✅ Nettoyage auto {status}")
        
        elif choice == '5':
            confirm = input("Réinitialiser tous les paramètres? (oui/non): ").strip().lower()
            if confirm in ['oui', 'o', 'yes', 'y']:
                config_manager.config = config_manager.default_config.copy()
                config_manager.save_config()
                print(f"✅ Paramètres réinitialisés")
        
        elif choice == '6':
            break
        
        else:
            print(f"❌ Choix invalide")

def download_sp3_file(config_manager):
    """Fonction de téléchargement SP3"""
    downloader = SP3CombinedDownloader(config_manager)
    
    # Vérifier les permissions d'écriture
    try:
        output_dir = Path(config_manager.get('output_directory'))
        test_file = output_dir / "test_permissions.tmp"
        with open(test_file, 'w') as f:
            f.write("test")
        test_file.unlink()
        print(f"✅ Permissions OK")
    except Exception as e:
        print(f"❌ Erreur permissions: {e}")
        input("Appuyez sur Entrée pour continuer...")
        return
    
    # Saisie date avec validation complète et suggestions
    while True:
        print(f"\n💡 CONSEILS POUR LES DATES:")
        print(f"• Ultra-rapides: Délai 3h minimum (essayez hier)")
        print(f"• Rapides: Délai 1 jour minimum")
        print(f"• Finaux: Délai 12+ jours minimum")
        
        # Suggestions de dates
        yesterday = datetime.now() - timedelta(days=1)
        last_week = datetime.now() - timedelta(days=7)
        print(f"• Suggestions: {yesterday.strftime('%d/%m/%Y')} ou {last_week.strftime('%d/%m/%Y')}")
        
        target_date = input("\nDate (DD/MM/YYYY): ").strip()
        
        if not target_date:
            print("❌ Veuillez entrer une date.")
            continue
            
        try:
            date_obj = datetime.strptime(target_date, "%d/%m/%Y")
            
            # Vérifier que la date n'est pas dans le futur
            if date_obj > datetime.now():
                print("❌ Date future invalide")
                continue
            
            # Vérifier que la date n'est pas trop ancienne (>5 ans)
            five_years_ago = datetime.now() - timedelta(days=5*365)
            if date_obj < five_years_ago:
                print(f"⚠️ Date très ancienne. Les données peuvent ne plus être disponibles.")
                confirm = input("Continuer quand même? (o/n): ").strip().lower()
                if confirm not in ['o', 'oui', 'y', 'yes']:
                    continue
            
            # Avertissement pour dates très récentes
            hours_ago = (datetime.now() - date_obj).total_seconds() / 3600
            if hours_ago < 6:
                print(f"⚠️ Date très récente ({hours_ago:.1f}h). Les ultra-rapides peuvent être indisponibles.")
                confirm = input("Continuer quand même? (o/n): ").strip().lower()
                if confirm not in ['o', 'oui', 'y', 'yes']:
                    continue
            
            print(f"✅ Date validée: {target_date}")
            break
            
        except ValueError:
            print("❌ Format invalide (utilisez DD/MM/YYYY)")
            continue
    
    # Téléchargement
    print(f"\n🚀 Début téléchargement...")
    print(f"⏱️ Priorité intervalles: {' > '.join(downloader.time_intervals)}")
    downloaded_file = downloader.smart_download_sp3(target_date)
    
    if downloaded_file:
        print(f"\n✅ SUCCÈS!")
        
        # Vérifier si le fichier existe réellement
        if not Path(downloaded_file).exists():
            print(f"❌ Erreur: Fichier non trouvé après téléchargement")
            input("Appuyez sur Entrée pour continuer...")
            return
        
        file_path = Path(downloaded_file)
        print(f"📁 Fichier: {file_path.name}")
        print(f"📂 Emplacement: {downloaded_file}")
        print(f"💾 Taille: {file_path.stat().st_size / (1024*1024):.2f} MB")
        
        # Vérifier si le fichier est compressé
        if file_path.suffix in ['.gz', '.Z']:
            print(f"⚠️ Fichier encore compressé - la décompression a échoué")
            print(f"💡 Vous pouvez utiliser le fichier compressé ou le décompresser manuellement")
        
        # Analyse automatique seulement si le fichier est décompressé
        print(f"\n🔍 Analyse...")
        analysis_success = downloader.analyze_sp3_file(downloaded_file)
        
        if analysis_success:
            print(f"\n✅ Fichier analysé avec succès!")
        else:
            print(f"\n⚠️ Analyse incomplète - fichier utilisable mais vérifiez le format")
        
        print(f"\n✅ Téléchargement terminé!")
        
    else:
        print(f"\n❌ Téléchargement échoué pour toutes les sources")
        print(f"\n💡 SUGGESTIONS:")
        print(f"• Essayez une date plus ancienne (hier ou la semaine dernière)")
        print(f"• Vérifiez votre token JWT dans les paramètres")
        print(f"• Les serveurs CDDIS peuvent être temporairement indisponibles")
    
    input("Appuyez sur Entrée pour continuer...")

def main():
    """Application principale avec menu"""
    
    # Initialiser la configuration
    config_manager = ConfigManager()
    
    while True:
        try:
            print("\n" + "=" * 50)
            print(f"🛰️  SP3 DOWNLOADER v2.2 ")
            print("=" * 50)
            print(f"👤 {config_manager.get('user_name')}")
            print(f"📁 {config_manager.get('output_directory')}")
            
            print(f"\n📋 MENU PRINCIPAL:")
            print(f"1. Télécharger fichier SP3")
            print(f"2. ⚙️  Paramètres")
            print(f"3. ❌ Quitter")
            
            choice = input("\nChoix (1-3): ").strip()
            
            if choice == '1':
                # Téléchargement SP3
                print("\n" + "-" * 30)
                download_sp3_file(config_manager)
            
            elif choice == '2':
                # Menu paramètres
                show_settings_menu(config_manager)
            
            elif choice == '3':
                print("👋 Au revoir!")
                break
            
            else:
                print("❌ Choix invalide")
        
        except KeyboardInterrupt:
            print("\n👋 Au revoir!")
            break
        except Exception as e:
            print(f"❌ Erreur: {e}")
            logger.error(f"Erreur main: {e}")
            input("Appuyez sur Entrée pour continuer...")

if __name__ == "__main__":
    main()