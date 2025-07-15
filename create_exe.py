import subprocess
import sys
import os
from pathlib import Path

def create_exe():
    """Crée l'exécutable SP3 avec changement de répertoire automatique"""
    
    print("🔧 CRÉATION DE L'EXÉCUTABLE SP3 DOWNLOADER")
    print("=" * 50)
    
    # CORRECTION : Changer vers le bon répertoire
    target_dir = Path(r"C:\1-Data\01-Projet\ProjetPY\Test_GNSS")
    source_file = "sp3exe.py"
    
    print(f"📂 Répertoire actuel: {os.getcwd()}")
    print(f"🎯 Changement vers: {target_dir}")
    
    # Vérifier que le répertoire cible existe
    if not target_dir.exists():
        print(f"❌ Répertoire cible non trouvé: {target_dir}")
        input("Appuyez sur Entrée pour fermer...")
        return
    
    # Changer vers le répertoire cible
    os.chdir(target_dir)
    print(f"✅ Changé vers: {os.getcwd()}")
    
    # Vérifier que le fichier source existe maintenant
    if not Path(source_file).exists():
        print(f"❌ Fichier {source_file} non trouvé dans {target_dir}")
        print(f"📋 Fichiers présents:")
        for file in Path(".").glob("*.py"):
            print(f"   - {file.name}")
        input("Appuyez sur Entrée pour fermer...")
        return
    
    print(f"✅ Fichier source trouvé: {source_file}")
    
    # Commande PyInstaller via python -m
    command = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console", 
        "--name=SP3_Downloader",
        "--clean",
        "--noconfirm",
        source_file
    ]
    
    print(f"🚀 Lancement de PyInstaller...")
    print(f"📋 Commande: {' '.join(command)}")
    
    try:
        # Exécuter PyInstaller
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        
        # Vérifier le résultat
        exe_path = Path("dist") / "SP3_Downloader.exe"
        
        if exe_path.exists():
            exe_size = exe_path.stat().st_size / (1024 * 1024)
            print(f"✅ SUCCÈS!")
            print(f"📁 Exécutable créé: {exe_path}")
            print(f"💾 Taille: {exe_size:.1f} MB")
            print(f"📂 Emplacement complet: {exe_path.absolute()}")
            
            print(f"\n🎉 VOTRE EXE EST PRÊT!")
            print(f"📋 Pour l'utiliser:")
            print(f"   1. Allez dans: {target_dir / 'dist'}")
            print(f"   2. Double-cliquez sur SP3_Downloader.exe")
            print(f"   3. Entrez votre date et c'est parti!")
            
            # Nettoyage optionnel
            print(f"\n🧹 Nettoyage des fichiers temporaires...")
            import shutil
            build_dir = Path("build")
            if build_dir.exists():
                shutil.rmtree(build_dir)
                print(f"✅ Dossier 'build' supprimé")
            
            for spec_file in Path(".").glob("*.spec"):
                spec_file.unlink()
                print(f"✅ Fichier {spec_file.name} supprimé")
            
        else:
            print(f"❌ Exe non créé")
            print(f"Sortie PyInstaller: {result.stdout}")
            if result.stderr:
                print(f"Erreurs: {result.stderr}")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur PyInstaller:")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
    except Exception as e:
        print(f"❌ Erreur: {e}")
    
    input("\nAppuyez sur Entrée pour fermer...")

def check_files():
    """Vérifie les fichiers disponibles"""
    target_dir = Path(r"C:\1-Data\01-Projet\ProjetPY\Test_GNSS")
    
    print("🔍 VÉRIFICATION DES FICHIERS")
    print("=" * 40)
    print(f"📂 Dossier cible: {target_dir}")
    
    if target_dir.exists():
        print(f"✅ Dossier existe")
        print(f"📋 Fichiers Python trouvés:")
        py_files = list(target_dir.glob("*.py"))
        if py_files:
            for file in py_files:
                size = file.stat().st_size
                print(f"   - {file.name} ({size} octets)")
        else:
            print(f"   ❌ Aucun fichier .py trouvé")
    else:
        print(f"❌ Dossier n'existe pas")
    
    input("\nAppuyez sur Entrée pour continuer...")

if __name__ == "__main__":
    # Vérifier d'abord les fichiers
    check_files()
    
    # Puis créer l'exe
    create_exe()