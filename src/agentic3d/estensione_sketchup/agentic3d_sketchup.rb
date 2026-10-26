# encoding: UTF-8
# Registrazione dell'estensione "Agentic 3D" in SketchUp (Estensioni > Gestione estensioni).
require 'sketchup.rb'
require 'extensions.rb'

module Agentic3D
  unless defined?(ESTENSIONE)
    ESTENSIONE = SketchupExtension.new('Agentic 3D', 'agentic3d_sketchup/principale')
    ESTENSIONE.description = 'Collega un modello di Agentic 3D e lo tiene aggiornato: oggetti con nome, tag e materiali, divisi in Muri, Solai, Serramenti e Arredi.'
    ESTENSIONE.version = '2.4.0'
    ESTENSIONE.creator = 'Andrea Lucarelli'
    ESTENSIONE.copyright = '© 2026 Andrea Lucarelli'
    Sketchup.register_extension(ESTENSIONE, true)
  end
end
