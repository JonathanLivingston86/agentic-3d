# encoding: UTF-8
#
# Agentic 3D per SketchUp: tiene aggiornato in SketchUp il modello costruito da Agentic 3D, senza chiudere e
# ricaricare nulla.
#
# Agentic 3D scrive un file "<Nome> per SketchUp.json" nella cartella Esportazioni del progetto. Questa estensione lo
# legge e crea un gruppo per ogni oggetto, con nome, tag e materiali, dentro un contenitore per categoria:
#
#   Muri        Tamponature, Tramezzi (un solido ciascuno per piano)
#   Solai       sottocontenitori Pavimenti, Soffitto, Controsoffitti, Balconi (il soffitto ha un tag a parte)
#   Serramenti  porte e finestre
#   Arredi      arredi e tessili
#
# Con più piani il nome del piano segue quello del contenitore. Quando il file cambia, si aggiornano SOLO gli oggetti
# cambiati:
#
#   - un oggetto spostato a mano resta dove è stato messo (lo spostamento si somma a quello del file);
#   - un oggetto non cambiato non viene ricostruito;
#   - un oggetto bloccato (Agentic 3D > Blocca selezione) non viene mai toccato, così si può modificare a mano;
#   - quello che è disegnato fuori dai gruppi di Agentic 3D non viene mai toccato;
#   - ogni aggiornamento è una sola operazione: Modifica > Annulla lo riporta com'era.
#
# Le facce arrivano già intere (le facce complanari sono fuse nel file, con i fori di porte e finestre) e si creano
# con add_face, come le disegnerebbe una persona: non c'è nessuno spigolo da cancellare dopo. Se SketchUp rifiuta un
# poligono si usa la sua riserva a triangoli, con gli spigoli interni ammorbiditi. Ogni oggetto viene controllato
# (area e, per i solidi, chiusura) e il risultato finisce in un rapporto ("Agentic 3D controllo.json", nella cartella
# temporanea di Windows) e, se qualcosa non torna, in un messaggio.

require 'sketchup.rb'
require 'json'
require 'tmpdir'

module Agentic3D
  DIZIONARIO = 'agentic3d'.freeze
  IMPOSTAZIONI = 'Agentic3D'.freeze
  INTERVALLO = 1.5 # secondi tra un controllo e l'altro
  VERSIONE_COSTRUZIONE = 6 # si alza quando cambia il modo di costruire: gli oggetti vecchi vengono rifatti
  VERSIONE_FILE_MINIMA = 4 # il file deve avere i poligoni fusi e le parti interne
  VERSIONE_FILE_MASSIMA = 6 # un file più nuovo chiede di aggiornare l'estensione
  MQ_PER_POLLICE2 = 0.0254 * 0.0254

  @percorso = nil
  @ultimo_cambio = nil
  @timer = nil
  @automatico = false
  @in_corso = false

  # ------------------------------------------------------------------ utilità
  def self.pt(v)
    Geom::Point3d.new(v[0].m, v[1].m, v[2].m)
  end

  def self.messaggio(testo)
    UI.messagebox(testo)
  end

  def self.cartella_temporanea
    Dir.tmpdir # Windows: %TEMP%; macOS: $TMPDIR
  end

  # ------------------------------------------------------------------ materiali e tag
  def self.crea_materiali(model, elenco)
    elenco.map do |m|
      mat = model.materials[m['nome']] || model.materials.add(m['nome'])
      mat.color = Sketchup::Color.new((m['colore'][0] * 255).round, (m['colore'][1] * 255).round, (m['colore'][2] * 255).round)
      mat.alpha = m['alpha'].to_f
      mat
    end
  end

  def self.tag(model, nome)
    model.layers[nome] || model.layers.add(nome)
  end

  # ------------------------------------------------------------------ riconoscere i vertici (spigoli lisci)
  # Un vertice di SketchUp si riconosce dal vertice del file più vicino (entro mezzo millimetro).
  CELLA_RICERCA = 0.002 # metri
  TOLLERANZA_VERTICE = 0.0005 # metri

  def self.cella_di(p)
    s = CELLA_RICERCA.m
    [(p.x / s).floor, (p.y / s).floor, (p.z / s).floor]
  end

  def self.griglia_punti(punti)
    g = {}
    punti.each_with_index { |p, i| (g[cella_di(p)] ||= []) << i }
    g
  end

  def self.trova_vertice(griglia, punti, p)
    cx, cy, cz = cella_di(p)
    migliore = nil
    minima = TOLLERANZA_VERTICE.m
    (-1..1).each do |a|
      (-1..1).each do |b|
        (-1..1).each do |c|
          (griglia[[cx + a, cy + b, cz + c]] || []).each do |i|
            d = p.distance(punti[i])
            if d <= minima
              minima = d
              migliore = i
            end
          end
        end
      end
    end
    migliore
  end

  def self.normale_newell(punti)
    nx = ny = nz = 0.0
    n = punti.length
    n.times do |i|
      a = punti[i]
      b = punti[(i + 1) % n]
      nx += (a.y - b.y) * (a.z + b.z)
      ny += (a.z - b.z) * (a.x + b.x)
      nz += (a.x - b.x) * (a.y + b.y)
    end
    Geom::Vector3d.new(nx, ny, nz)
  end

  # area di un triangolo in pollici quadrati (unità interne di SketchUp)
  def self.area_triangolo(a, b, c)
    (b - a).cross(c - a).length / 2.0
  end

  # ------------------------------------------------------------------ costruzione di un oggetto
  def self.punti_dell_oggetto(ob)
    ob['vertici'].each_slice(3).map { |x, y, z| Geom::Point3d.new(x.m, y.m, z.m) }
  end

  def self.aggiungi_faccia(ents, pts)
    ents.add_face(pts)
  rescue ArgumentError, RuntimeError
    nil
  end

  # Un poligono con i suoi fori: faccia esterna, poi ogni foro come faccia interna che si cancella (il modo
  # documentato da SketchUp per fare un foro). Restituisce la faccia, o nil se l'area non torna.
  def self.crea_poligono(ents, punti, anelli, area_attesa, create)
    faccia = aggiungi_faccia(ents, anelli[0].map { |i| punti[i] })
    return nil if faccia.nil?
    anelli[1..-1].each do |foro|
      interna = aggiungi_faccia(ents, foro.map { |i| punti[i] })
      if interna.nil?
        faccia.erase! if faccia.valid?
        return nil
      end
      next if interna == faccia || create[interna]
      interna.erase! if interna.valid?
    end
    return nil unless faccia.valid?
    if (faccia.area - area_attesa).abs > [area_attesa * 1e-3, 0.02].max # 0,02 pollici quadrati: 0,13 cm2
      faccia.erase!
      return nil
    end
    faccia
  end

  # area delle facce, compresi i gruppi interni (parti di un serramento o di un arredo)
  def self.area_m2(ents)
    ents.grep(Sketchup::Face).sum(&:area) * MQ_PER_POLLICE2 + ents.grep(Sketchup::Group).sum { |g| area_m2(g.entities) }
  end

  def self.facce_totali(ents)
    ents.grep(Sketchup::Face).length + ents.grep(Sketchup::Group).sum { |g| facce_totali(g.entities) }
  end

  # gruppi e componenti: gli oggetti di Agentic 3D sono l'uno o l'altro
  def self.oggetti_in(ents)
    ents.select { |e| e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance) }
  end

  def self.entita_di(x)
    x.is_a?(Sketchup::ComponentInstance) ? x.definition.entities : x.entities
  end

  # solido: l'oggetto stesso, oppure (se è fatto di parti) ognuna delle sue parti
  def self.solido?(oggetto)
    return nil unless oggetto.respond_to?(:manifold?)
    interni = entita_di(oggetto).grep(Sketchup::Group)
    return oggetto.manifold? if interni.empty?
    interni.all?(&:manifold?)
  end

  def self.area_ok(area, attesa)
    (area - attesa).abs <= [attesa * 1e-3, 1e-4].max
  end

  # Crea il gruppo di un oggetto dentro `ents_genitore` e lo controlla. Restituisce [gruppo, problemi, esito].
  def self.costruisci_oggetto(model, ents_genitore, ob, materiali)
    gruppo = ents_genitore.add_group
    begin
      gruppo.name = ob['nome']
      conti = costruisci_geometria(gruppo.entities, ob, materiali)
      gruppo.transformation = Geom::Transformation.new(pt(ob['origine']))
      problemi, esito = controlla_costruito(gruppo.entities, gruppo, ob, conti)
      segna(model, gruppo, ob)
      [gruppo, problemi, esito]
    rescue StandardError
      gruppo.erase! if gruppo.valid?
      raise
    end
  end

  # Definizione di un componente (oggetti ripetuti): si costruisce una volta; se cambia, si svuota e si rifà e tutte
  # le copie nel modello cambiano insieme. Restituisce [definizione, problemi, esito] (problemi nil se invariata).
  def self.prepara_definizione(model, d, materiali, forza)
    defn = model.definitions[d['nome']]
    if defn && !forza && defn.get_attribute(DIZIONARIO, 'impronta') == d['impronta'] &&
       defn.get_attribute(DIZIONARIO, 'versione') == VERSIONE_COSTRUZIONE
      return [defn, nil, nil]
    end
    if defn
      defn.entities.clear!
    else
      defn = model.definitions.add(d['nome'])
    end
    conti = costruisci_geometria(defn.entities, d, materiali)
    problemi, esito = controlla_costruito(defn.entities, nil, d, conti)
    defn.set_attribute(DIZIONARIO, 'impronta', d['impronta'])
    defn.set_attribute(DIZIONARIO, 'versione', VERSIONE_COSTRUZIONE)
    defn.set_attribute(DIZIONARIO, 'area', d['area'])
    defn.set_attribute(DIZIONARIO, 'chiuso', d['chiuso'] ? true : false)
    [defn, problemi, esito]
  end

  # Copia di un componente nella posizione del file (matrice 4x4 per colonne, traslazione in metri).
  def self.crea_copia(model, ents_genitore, ob, defn)
    a = ob['matrice'].dup
    (12..14).each { |k| a[k] = a[k].to_f.m }
    copia = ents_genitore.add_instance(defn, Geom::Transformation.new(a))
    copia.name = ob['nome']
    segna(model, copia, ob)
    copia.set_attribute(DIZIONARIO, 'area', defn.get_attribute(DIZIONARIO, 'area'))
    copia.set_attribute(DIZIONARIO, 'chiuso', defn.get_attribute(DIZIONARIO, 'chiuso'))
    problemi = []
    problemi << 'non è un solido chiuso' if defn.get_attribute(DIZIONARIO, 'chiuso') && solido?(copia) == false
    [copia, problemi]
  end

  def self.segna(model, oggetto, ob)
    oggetto.layer = tag(model, ob['tag'])
    oggetto.set_attribute(DIZIONARIO, 'progetto', ob['progetto'])
    oggetto.set_attribute(DIZIONARIO, 'nome', ob['nome'])
    oggetto.set_attribute(DIZIONARIO, 'impronta', ob['impronta'])
    oggetto.set_attribute(DIZIONARIO, 'tipo', ob['tipo'])
    oggetto.set_attribute(DIZIONARIO, 'in', ob['contenitore'])
    oggetto.set_attribute(DIZIONARIO, 'versione', VERSIONE_COSTRUZIONE)
    oggetto.set_attribute(DIZIONARIO, 'area', ob['area']) if ob['area']
    oggetto.set_attribute(DIZIONARIO, 'chiuso', ob['chiuso'] ? true : false) unless ob['chiuso'].nil?
    oggetto.set_attribute(DIZIONARIO, 'generato', oggetto.transformation.to_a)
  end

  # Facce di un oggetto dentro `radice` (le entità di un gruppo o di una definizione). Restituisce i conteggi.
  def self.costruisci_geometria(radice, ob, materiali)
    # un oggetto fatto di più solidi (telaio, vetro, maniglia...) ha un gruppo per parte: due solidi che si toccano
    # nello stesso gruppo fonderebbero le facce a contatto
    parti = (ob['parti'] || []).map do |nome|
      g = radice.add_group
      g.name = nome
      g
    end
    ents_di = ->(n) { parti.empty? ? radice : parti[ob['parte'][n]].entities }
    tutte = parti.empty? ? [radice] : parti.map(&:entities)
    punti = punti_dell_oggetto(ob)
    triangoli = Hash.new { |h, k| h[k] = [] }
    ob['triangoli'].each { |t| triangoli[t[0]] << t[1, 3] }
    # un poligono che è già un triangolo (superfici curve) è la riserva di sé stesso
    ob['poligoni'].each_with_index do |pol, n|
      triangoli[n] = [pol[1]] if pol.length == 2 && pol[1].length == 3 && !triangoli.key?(n)
    end
    create = {}
    riserve = 0
    rifiutati = 0

    ob['poligoni'].each_with_index do |pol, n|
      mat = materiali[pol[0]]
      anelli = pol[1..-1]
      attesa = normale_newell(anelli[0].map { |i| punti[i] })
      area_attesa = triangoli[n].sum { |a, b, c| area_triangolo(punti[a], punti[b], punti[c]) }
      facce = []
      ents = ents_di.call(n)
      f = crea_poligono(ents, punti, anelli, area_attesa, create)
      if f
        facce << f
      else
        riserve += 1
        triangoli[n].each do |t|
          tf = aggiungi_faccia(ents, t.map { |i| punti[i] })
          tf ? facce << tf : rifiutati += 1
        end
        # spigoli interni della riserva: ammorbiditi, la faccia si vede intera; non si cancellano
        facce.each do |x|
          x.edges.each do |e|
            next unless e.faces.length == 2 && e.faces.all? { |q| facce.include?(q) }
            e.soft = true
            e.smooth = true
          end
        end
      end
      facce.each do |x|
        next unless x.valid?
        x.reverse! if x.normal.dot(attesa) < 0
        x.material = mat
        x.back_material = mat
        create[x] = true
      end
    end

    tutte.each do |ents|
      # spigoli rimasti senza facce (bordi dei poligoni rifiutati): via
      sciolti = ents.grep(Sketchup::Edge).select { |e| e.faces.empty? }
      ents.erase_entities(sciolti) unless sciolti.empty?
    end

    # spigoli delle superfici curve: ammorbiditi
    unless ob['lisci'].empty?
      griglia = griglia_punti(punti)
      lisci = {}
      ob['lisci'].each { |i, j| lisci[[i, j].sort] = true }
      tutte.each do |ents|
        ents.grep(Sketchup::Edge).each do |e|
          i = trova_vertice(griglia, punti, e.start.position)
          j = trova_vertice(griglia, punti, e.end.position)
          next if i.nil? || j.nil? || !lisci[[i, j].sort]
          e.soft = true
          e.smooth = true
        end
      end
    end
    { 'parti' => parti.length, 'riserve' => riserve, 'rifiutati' => rifiutati }
  end

  # Confronto tra ciò che SketchUp ha creato e ciò che il file dichiara. `oggetto` nil = definizione (il solido si
  # controlla sulle copie).
  def self.controlla_costruito(radice, oggetto, ob, conti)
    area = area_m2(radice)
    solido = oggetto ? solido?(oggetto) : nil
    problemi = []
    problemi << "#{conti['riserve']} facce create a triangoli (riserva)" if conti['riserve'] > 0
    problemi << "#{conti['rifiutati']} triangoli rifiutati da SketchUp" if conti['rifiutati'] > 0
    problemi << "area #{area.round(3)} m2 invece di #{ob['area']}" unless area_ok(area, ob['area'].to_f)
    problemi << 'non è un solido chiuso' if ob['chiuso'] && solido == false
    esito = { 'nome' => ob['nome'], 'poligoni' => ob['poligoni'].length, 'parti' => conti['parti'],
              'facce' => facce_totali(radice), 'riserve' => conti['riserve'], 'rifiutati' => conti['rifiutati'],
              'area_attesa' => ob['area'], 'area' => area.round(5), 'chiuso_atteso' => ob['chiuso'] ? true : false,
              'solido' => solido, 'problemi' => problemi }
    [problemi, esito]
  end

  # ------------------------------------------------------------------ contenitori e ricerca degli oggetti
  def self.e_contenitore?(g)
    !g.get_attribute(DIZIONARIO, 'contenitore').nil?
  end

  def self.contenitori_del_progetto(model, progetto)
    model.entities.grep(Sketchup::Group).select do |g|
      g.get_attribute(DIZIONARIO, 'progetto') == progetto && e_contenitore?(g)
    end
  end

  # tutti i gruppi-oggetto: al primo livello (versioni precedenti) o dentro i contenitori e i loro sottocontenitori
  # (Solai > Pavimenti); progetto nil = tutti
  def self.gruppi_del_progetto(model, progetto = nil)
    out = []
    raccogli = lambda do |ents, filtro|
      oggetti_in(ents).each do |g|
        p = g.get_attribute(DIZIONARIO, 'progetto')
        next if p.nil? || (filtro && p != filtro)
        if g.is_a?(Sketchup::Group) && e_contenitore?(g)
          raccogli.call(g.entities, p)
        else
          out << g
        end
      end
    end
    raccogli.call(model.entities, progetto)
    out
  end

  # contenitore per categoria, senza tag: i tag stanno sugli oggetti, così si spegne una categoria alla volta.
  # "Solai/Pavimenti" è il sottocontenitore Pavimenti dentro Solai: si spegne con un clic senza toccare il resto.
  def self.contenitore(model, progetto, nome, cache)
    return cache[nome] if cache[nome] && cache[nome].valid?
    parti = nome.split('/')
    if parti.length > 1
      genitore = contenitore(model, progetto, parti[0..-2].join('/'), cache)
      ents = genitore.entities
      c = ents.grep(Sketchup::Group).find { |g| g.get_attribute(DIZIONARIO, 'contenitore') == nome }
    else
      ents = model.entities
      c = contenitori_del_progetto(model, progetto).find { |g| g.get_attribute(DIZIONARIO, 'contenitore') == nome }
    end
    if c.nil?
      c = ents.add_group
      c.name = parti.last
      c.set_attribute(DIZIONARIO, 'progetto', progetto)
      c.set_attribute(DIZIONARIO, 'contenitore', nome)
    end
    c.layer = model.layers[0]
    cache[nome] = c
  end

  # contenitori vuoti eliminati, dai sottocontenitori in su (un Solai rimasto senza figli sparisce anch'esso)
  def self.togli_contenitori_vuoti(ents)
    ents.grep(Sketchup::Group).select { |g| e_contenitore?(g) }.each do |c|
      togli_contenitori_vuoti(c.entities)
      c.erase! if c.valid? && oggetti_in(c.entities).empty?
    end
  end

  # ------------------------------------------------------------------ rapporto di controllo e registro
  def self.percorso_registro
    File.join(cartella_temporanea, 'Agentic 3D registro.txt')
  end

  def self.percorso_controllo
    File.join(cartella_temporanea, 'Agentic 3D controllo.json')
  end

  def self.registra(testo)
    File.open(percorso_registro, 'a:UTF-8') { |f| f.puts("#{Time.now.strftime('%Y-%m-%d %H:%M:%S')}  #{testo}") }
  rescue StandardError
    nil
  end

  def self.scrivi_controllo(dati)
    File.write(percorso_controllo, JSON.pretty_generate(dati), encoding: 'UTF-8')
  rescue StandardError => e
    registra("rapporto di controllo non scritto: #{e.class}: #{e.message}")
  end

  # Gli errori dentro un comando di menu SketchUp li scrive solo nella Console Ruby: qui finiscono anche nel registro
  # e in un messaggio.
  def self.protetto(azione)
    registra("comando: #{azione}")
    yield
  rescue Exception => e # rubocop:disable Lint/RescueException
    registra("ERRORE in #{azione}: #{e.class}: #{e.message}\n  #{(e.backtrace || []).first(8).join("\n  ")}")
    messaggio("Agentic 3D: errore in \"#{azione}\".\n#{e.class}: #{e.message}\n\nDettagli: Agentic 3D > Strumenti > Apri registro.")
  end

  def self.apri_registro
    UI.openURL("file:///#{percorso_registro.tr('\\', '/')}")
  end

  # ------------------------------------------------------------------ aggiornamento
  # Restituisce true se l'aggiornamento è riuscito (o non serviva), false se il file non era leggibile o
  # l'operazione è stata annullata: in quel caso il controllo automatico riprova al giro dopo.
  def self.aggiorna(percorso, silenzioso = false, forza = false)
    return false if @in_corso
    @in_corso = true
    begin
      dati = begin
        JSON.parse(File.read(percorso, encoding: 'UTF-8'))
      rescue StandardError => e
        registra("lettura di #{percorso}: #{e.class}: #{e.message}")
        return false # file ancora in scrittura o non valido
      end
      unless dati.is_a?(Hash) && dati['formato'] == 'agentic3d'
        registra("#{percorso}: non è un file di Agentic 3D")
        return false
      end
      if dati['versione'].to_i > VERSIONE_FILE_MASSIMA
        @rifiutato = cambio_del_file # l'avviso compare una volta per ogni cambio del file, non a ogni controllo
        messaggio("#{File.basename(percorso)} è stato scritto da una versione più recente di Agentic 3D.\n" \
                  'Installare l\'estensione aggiornata e riavviare SketchUp.')
        return false
      end
      if dati['versione'].to_i < VERSIONE_FILE_MINIMA
        @rifiutato = cambio_del_file
        messaggio("#{File.basename(percorso)} è stato scritto da una versione precedente di Agentic 3D.\n" \
                  'Rigenerare l\'esportazione e riprovare.')
        return false
      end
      model = Sketchup.active_model
      progetto = dati['progetto']
      esistenti = {}
      gruppi_del_progetto(model, progetto).each { |g| esistenti[g.get_attribute(DIZIONARIO, 'nome')] = g }
      errori = []
      esiti = []
      creati = aggiornati = invariati = rimossi = bloccati = 0
      inizio = Time.now
      model.start_operation("Agentic 3D: aggiorna #{progetto}", true)
      begin
        materiali = crea_materiali(model, dati['materiali'])
        nomi = []
        cache = {}
        # componenti: ogni definizione si prepara una volta, prima delle copie
        definizioni = {}
        (dati['definizioni'] || []).each do |d|
          defn, problemi, esito = prepara_definizione(model, d, materiali, forza)
          definizioni[d['nome']] = defn
          next if problemi.nil?
          problemi.each { |x| errori << "componente #{d['nome']}: #{x}" }
          esiti << esito.merge('componente' => true)
        end
        dati['oggetti'].each do |ob|
          ob['progetto'] = progetto
          nomi << ob['nome']
          vecchio = esistenti[ob['nome']]
          delta = nil
          if vecchio
            if vecchio.get_attribute(DIZIONARIO, 'bloccato')
              bloccati += 1
              next
            end
            if !forza && vecchio.get_attribute(DIZIONARIO, 'impronta') == ob['impronta'] &&
               vecchio.get_attribute(DIZIONARIO, 'versione') == VERSIONE_COSTRUZIONE &&
               vecchio.get_attribute(DIZIONARIO, 'in') == ob['contenitore']
              invariati += 1
              next
            end
            # lo spostamento fatto a mano si somma alla nuova posizione del file
            t_generata = Geom::Transformation.new(vecchio.get_attribute(DIZIONARIO, 'generato'))
            delta = vecchio.transformation * t_generata.inverse
          end
          genitore = if ob['contenitore'].to_s.empty?
                       model.entities
                     else
                       contenitore(model, progetto, ob['contenitore'], cache).entities
                     end
          begin
            if ob['componente']
              defn = definizioni[ob['componente']]
              raise ArgumentError, "componente #{ob['componente']} mancante nel file" if defn.nil?
              gruppo, problemi = crea_copia(model, genitore, ob, defn)
              esito = { 'nome' => ob['nome'], 'componente' => ob['componente'], 'solido' => solido?(gruppo),
                        'problemi' => problemi }
            else
              gruppo, problemi, esito = costruisci_oggetto(model, genitore, ob, materiali)
            end
          rescue StandardError => e
            errori << "#{ob['nome']}: #{e.class}: #{e.message}" # il vecchio resta com'era
            esiti << { 'nome' => ob['nome'], 'errore' => "#{e.class}: #{e.message}" }
            next
          end
          vecchio.erase! if vecchio && vecchio.valid? # dopo aver creato il nuovo: un contenitore vuoto sparirebbe
          gruppo.transformation = delta * gruppo.transformation if delta
          delta ? aggiornati += 1 : creati += 1
          problemi.each { |p| errori << "#{ob['nome']}: #{p}" }
          esiti << esito
        end
        esistenti.each do |nome, g|
          next if nomi.include?(nome) || !g.valid?
          if g.get_attribute(DIZIONARIO, 'bloccato')
            bloccati += 1
          else
            g.erase!
            rimossi += 1
          end
        end
        contenitori_del_progetto(model, progetto).each do |c|
          togli_contenitori_vuoti(c.entities)
          c.erase! if c.valid? && oggetti_in(c.entities).empty?
        end
        model.commit_operation
      rescue StandardError => e
        model.abort_operation
        registra("aggiornamento annullato: #{e.class}: #{e.message}\n  #{(e.backtrace || []).first(8).join("\n  ")}")
        messaggio("Agentic 3D: aggiornamento annullato.\n#{e.class}: #{e.message}")
        return false
      end
      riepilogo = "#{progetto}: #{creati} nuovi, #{aggiornati} aggiornati, #{invariati} invariati, #{rimossi} rimossi, #{bloccati} bloccati"
      registra(riepilogo)
      errori.each { |x| registra("  #{x}") }
      scrivi_controllo('quando' => Time.now.strftime('%Y-%m-%d %H:%M:%S'), 'file' => percorso,
                       'versione_costruzione' => VERSIONE_COSTRUZIONE, 'sketchup' => Sketchup.version,
                       'secondi' => (Time.now - inizio).round(2), 'riepilogo' => riepilogo, 'oggetti' => esiti)
      Sketchup.status_text = "Agentic 3D: #{riepilogo}"
      testo = errori.empty? ? riepilogo : "#{riepilogo}\n\nDa verificare:\n#{errori.first(25).join("\n")}"
      messaggio(testo) if !silenzioso || !errori.empty?
      true
    ensure
      @in_corso = false
    end
  end

  # Controlla gli oggetti presenti nel modello: area e chiusura rispetto al file.
  def self.controlla_modello
    model = Sketchup.active_model
    righe = []
    esiti = []
    gruppi = gruppi_del_progetto(model)
    gruppi.each do |g|
      next if g.get_attribute(DIZIONARIO, 'nome').nil?
      attesa = g.get_attribute(DIZIONARIO, 'area').to_f
      area = area_m2(entita_di(g))
      solido = solido?(g)
      riga = []
      riga << "area #{area.round(3)} m2 invece di #{attesa.round(3)}" unless area_ok(area, attesa)
      riga << 'non è un solido chiuso' if g.get_attribute(DIZIONARIO, 'chiuso') && solido == false
      riga << 'costruito da una versione precedente' if g.get_attribute(DIZIONARIO, 'versione') != VERSIONE_COSTRUZIONE
      righe << "#{g.name}: #{riga.join(', ')}" unless riga.empty?
      esiti << { 'nome' => g.name, 'facce' => facce_totali(entita_di(g)), 'area_attesa' => attesa,
                 'area' => area.round(5), 'solido' => solido, 'problemi' => riga }
    end
    scrivi_controllo('quando' => Time.now.strftime('%Y-%m-%d %H:%M:%S'), 'controllo' => true,
                     'versione_costruzione' => VERSIONE_COSTRUZIONE, 'sketchup' => Sketchup.version, 'oggetti' => esiti)
    if esiti.empty?
      messaggio('Nessun oggetto di Agentic 3D nel modello.')
    elsif righe.empty?
      messaggio("Controllati #{esiti.length} oggetti: aree e solidi corrispondono al file.")
    else
      messaggio("Controllati #{esiti.length} oggetti. Da verificare:\n#{righe.first(30).join("\n")}")
    end
  end

  # ------------------------------------------------------------------ collegamento al file
  def self.cambio_del_file
    File.mtime(@percorso).to_f
  rescue StandardError
    nil
  end

  def self.usa_file(scelto)
    unless File.file?(scelto)
      messaggio("File non trovato:\n#{scelto}")
      return
    end
    @percorso = scelto
    Sketchup.write_default(IMPOSTAZIONI, 'percorso', scelto)
    # il collegamento si salva nel modello: riaprendo questo .skp ci si ricollega da soli, gli altri non si toccano
    Sketchup.active_model.set_attribute(DIZIONARIO, 'percorso', scelto)
    registra("collegato: #{scelto}")
    cambio = cambio_del_file
    if aggiorna(scelto)
      @ultimo_cambio = cambio
    else
      messaggio("Impossibile leggere il modello:\n#{scelto}\n\nServe un file \"per SketchUp.json\" esportato da Agentic 3D. " \
                'Dettagli: Agentic 3D > Strumenti > Apri registro.')
    end
    attiva_automatico(true)
  end

  # Finestra di scelta del file; se SketchUp non riesce ad aprirla, si chiede il percorso in un campo di testo.
  def self.collega
    inizio = Sketchup.read_default(IMPOSTAZIONI, 'percorso', '').to_s
    cartella = inizio.empty? ? nil : File.dirname(inizio)
    cartella = nil unless cartella && File.directory?(cartella)
    scelto = begin
      UI.openpanel('Scegli il file "per SketchUp.json"', cartella, 'Modello Agentic 3D|*.json||')
    rescue StandardError => e
      registra("finestra di scelta non disponibile: #{e.class}: #{e.message}")
      risposta = UI.inputbox(['Percorso del file "per SketchUp.json"'], [inizio], 'Agentic 3D: collega modello')
      risposta ? risposta[0].to_s.strip.delete('"') : nil
    end
    return if scelto.nil? || scelto.empty?
    usa_file(scelto)
  end

  def self.aggiorna_ora(forza = false)
    if @percorso.nil?
      collega
    else
      cambio = cambio_del_file
      unless esci_dai_gruppi_del_progetto
        messaggio('Uscire dal gruppo aperto e riprovare.')
        return
      end
      @ultimo_cambio = cambio if aggiorna(@percorso, false, forza)
    end
  end

  # Se si sta lavorando dentro un gruppo, l'aggiornamento non può ricostruire gli oggetti in sicurezza. Se il gruppo
  # aperto è un contenitore o un oggetto di Agentic 3D (aperto solo per guardare), lo si chiude e si aggiorna; se è
  # geometria dell'utente si aspetta e lo si dice nella barra di stato. Restituisce true se si può aggiornare.
  def self.esci_dai_gruppi_del_progetto
    model = Sketchup.active_model
    percorso = model.active_path
    return true if percorso.nil?
    if percorso.all? { |e| e.get_attribute(DIZIONARIO, 'nome') || e.attribute_dictionary(DIZIONARIO) }
      model.close_active until model.active_path.nil?
      true
    else
      Sketchup.status_text = 'Agentic 3D: modifiche in attesa. Uscire dal gruppo aperto per applicarle.'
      false
    end
  end

  def self.attiva_automatico(si)
    @automatico = si
    UI.stop_timer(@timer) if @timer
    @timer = nil
    return unless si
    @timer = UI.start_timer(INTERVALLO, true) do
      next if @in_corso || @percorso.nil?
      begin
        cambio = cambio_del_file
        next unless cambio && cambio != @ultimo_cambio && cambio != @rifiutato
        next unless esci_dai_gruppi_del_progetto
        @ultimo_cambio = cambio if aggiorna(@percorso, true)
      rescue StandardError => e
        registra("ERRORE nell'aggiornamento automatico: #{e.class}: #{e.message}")
      end
    end
  end

  def self.scollega
    attiva_automatico(false)
    @percorso = nil
    model = Sketchup.active_model
    model.delete_attribute(DIZIONARIO, 'percorso') if model && model.get_attribute(DIZIONARIO, 'percorso')
    Sketchup.status_text = 'Agentic 3D: scollegato'
  end

  # All'avvio e quando si apre un modello: se il modello era collegato a un file che esiste ancora, si riprende il
  # controllo automatico senza ricostruire nulla (si aggiorna solo quando il file cambia). Un modello non collegato
  # ferma il controllo, così un progetto non entra mai in un modello diverso.
  def self.ricollega(model)
    percorso = model && model.get_attribute(DIZIONARIO, 'percorso')
    if percorso && File.file?(percorso)
      @percorso = percorso
      @ultimo_cambio = cambio_del_file
      attiva_automatico(true)
      registra("ricollegato all'apertura: #{percorso}")
      Sketchup.status_text = "Agentic 3D: collegato a #{File.basename(percorso)}"
    else
      attiva_automatico(false)
      @percorso = nil
    end
  rescue StandardError => e
    registra("ricollegamento non riuscito: #{e.class}: #{e.message}")
  end

  class Osservatore < Sketchup::AppObserver
    def onOpenModel(model)
      Agentic3D.ricollega(model)
    end

    def onNewModel(model)
      Agentic3D.ricollega(model)
    end
  end

  # ------------------------------------------------------------------ blocco di oggetti
  def self.imposta_blocco(valore)
    sel = oggetti_in(Sketchup.active_model.selection).select { |g| g.get_attribute(DIZIONARIO, 'nome') }
    if sel.empty?
      messaggio('Selezionare uno o più oggetti di Agentic 3D.')
      return
    end
    Sketchup.active_model.start_operation(valore ? 'Agentic 3D: blocca' : 'Agentic 3D: sblocca', true)
    sel.each { |g| g.set_attribute(DIZIONARIO, 'bloccato', valore ? true : nil) }
    Sketchup.active_model.commit_operation
    Sketchup.status_text = "Agentic 3D: #{sel.length} oggetti #{valore ? 'bloccati' : 'sbloccati'}"
  end

  # ------------------------------------------------------------------ menu
  unless file_loaded?(__FILE__)
    menu = UI.menu('Extensions').add_submenu('Agentic 3D')
    menu.add_item('Collega modello...') { protetto('Collega modello') { collega } }
    menu.add_item('Aggiorna') { protetto('Aggiorna') { aggiorna_ora } }
    voce = menu.add_item('Aggiornamento automatico') do
      protetto('Aggiornamento automatico') { @percorso.nil? ? collega : attiva_automatico(!@automatico) }
    end
    menu.set_validation_proc(voce) { @automatico ? MF_CHECKED : MF_UNCHECKED }
    menu.add_separator
    menu.add_item('Blocca selezione') { protetto('Blocca selezione') { imposta_blocco(true) } }
    menu.add_item('Sblocca selezione') { protetto('Sblocca selezione') { imposta_blocco(false) } }
    menu.add_separator
    strumenti = menu.add_submenu('Strumenti')
    strumenti.add_item('Ricostruisci tutto') { protetto('Ricostruisci tutto') { aggiorna_ora(true) } }
    strumenti.add_item('Controlla modello') { protetto('Controlla modello') { controlla_modello } }
    strumenti.add_item('Apri registro') { protetto('Apri registro') { apri_registro } }
    menu.add_item('Scollega') { protetto('Scollega') { scollega } }
    Sketchup.add_observer(Osservatore.new)
    UI.start_timer(1.0, false) { ricollega(Sketchup.active_model) }   # il modello aperto all'avvio
    file_loaded(__FILE__)
  end
end
