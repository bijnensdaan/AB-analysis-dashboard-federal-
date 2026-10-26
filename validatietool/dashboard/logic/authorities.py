"""Conservatieve hoofdingherkenning; geen afleiding uit onderwerp of bestuursniveau.

Namen, historische namen en taalvarianten staan in een controleerbare referentielijst.
Beleidsdomeinen zijn brede dashboardrubrieken, geen historische bevoegdheidstoets.
Een algemene overheid/regering levert op zichzelf geen beleidsdomein op.
"""
import re
import unicodedata

SOURCES={
 'federal_nl':'https://www.belgium.be/nl/over_belgie/overheid/federale_overheid/federale_en_programmatorische_overheidsdiensten',
 'federal_fr':'https://www.belgium.be/fr/la_belgique/pouvoirs_publics/autorites_federales/services_publics_federaux_et_de_programmation',
 'federal_de':'https://socialsecurity.belgium.be/sites/default/files/content/docs/de/kontakt/brochure-nutzliche-informationen-de.pdf',
 'history':'https://bosa.belgium.be/sites/default/files/publications/documents/broch_copernicus_fr.pdf',
 'vlaanderen':'https://www.vlaanderen.be/uw-overheid/werking-en-structuur-van-de-vlaamse-overheid/de-structuur-en-werking-van-de-vlaamse-overheid',
 'vlaamse_regering':'https://www.vlaanderen.be/uw-overheid/werking-en-structuur-van-de-vlaamse-overheid/overheid-regering-en-parlement',
 'wallonie':'https://spw.wallonie.be/administrations/service-public-de-wallonie',
 'bruxelles':'https://servicepublic.brussels/qui-sommes-nous/',
 'cfwb':'https://gouvernement.cfwb.be/home/presse--actualites/ordres-du-jour/ordresdujour/gouvernement-conjoint-fwb-rw-du-11-juin-2026.html',
 'dg':'https://www.belgium.be/de/authority_level/deutschsprachige_gemeinschaft',
 'ggc':'https://www.ccc-ggc.brussels/fr/coll%C3%A8ge-r%C3%A9uni',
}


def reference_list():
    """Expliciete naamvarianten; historische ministeries behouden hun historische naam."""
    rows=[]
    def add(key,name,domain,aliases,source,kind='administratie',historical=False):
        rows.append({'id':key,'orgaan':name,'beleidsdomein':domain,'aliases':aliases,
                     'source_keys':source,'kind':kind,'historical':historical})
    federal=[
      ('kanselarij','Kanselarij van de Eerste Minister','Chancellerie du Premier Ministre','Kanzlei des Premierministers','Algemeen bestuur'),
      ('bosa','Beleid en Ondersteuning','Stratégie et Appui','Politik und Unterstützung','Algemeen bestuur'),
      ('buitenland','Buitenlandse Zaken, Buitenlandse Handel en Ontwikkelingssamenwerking','Affaires étrangères, Commerce extérieur et Coopération au Développement','Auswärtige Angelegenheiten, Außenhandel und Entwicklungszusammenarbeit','Buitenlandse zaken en ontwikkelingssamenwerking'),
      ('binnenland','Binnenlandse Zaken','Intérieur','Inneres','Binnenlandse zaken'),
      ('financien','Financiën','Finances','Finanzen','Financiën'),
      ('mobiliteit','Mobiliteit en Vervoer','Mobilité et Transports','Mobilität und Transportwesen','Mobiliteit en vervoer'),
      ('werk','Werkgelegenheid, Arbeid en Sociaal Overleg','Emploi, Travail et Concertation sociale','Beschäftigung, Arbeit und Soziale Konzertierung','Werk en sociaal overleg'),
      ('sociale_zekerheid','Sociale Zekerheid','Sécurité sociale','Soziale Sicherheit','Sociale zekerheid'),
      ('gezondheid','Volksgezondheid, Veiligheid van de Voedselketen en Leefmilieu','Santé publique, Sécurité de la Chaîne alimentaire et Environnement','Volksgesundheit, Sicherheit der Nahrungsmittelkette und Umwelt','Volksgezondheid, voedselveiligheid en leefmilieu'),
      ('justitie','Justitie','Justice','Justiz','Justitie'),
      ('economie','Economie, KMO, Middenstand en Energie','Economie, PME, Classes moyennes et Energie','Wirtschaft, KMB, Mittelstand und Energie','Economie en energie'),
    ]
    for key,nl,fr,de,domain in federal:
        add('fod_'+key,'FOD '+nl,domain,['Federale Overheidsdienst '+nl,'Service public fédéral '+fr,'Föderaler Öffentlicher Dienst '+de],['federal_nl','federal_fr','federal_de'])
    add('defensie','Ministerie van Defensie','Defensie',['Ministerie van Defensie','Ministère de la Défense','Ministerium der Landesverteidigung'],['federal_nl','federal_fr'])
    add('pod_integratie','POD Maatschappelijke Integratie','Maatschappelijke integratie',[
      'Programmatorische Federale Overheidsdienst Maatschappelijke Integratie, Armoedebestrijding, Sociale Economie en Grootstedenbeleid',
      'Service public fédéral de programmation Intégration sociale, Lutte contre la Pauvreté, Economie sociale et Politique des Grandes Villes',
      'Föderaler Öffentlicher Programmierungsdienst Sozialeingliederung, Armutsbekämpfung, Sozialwirtschaft und Politik der Großstädte'],['federal_nl','federal_fr','federal_de'])
    add('pod_wetenschap','POD Wetenschapsbeleid','Wetenschapsbeleid',[
      'Programmatorische Federale Overheidsdienst Wetenschapsbeleid','Service public fédéral de programmation Politique scientifique','Föderaler Öffentlicher Programmierungsdienst Wissenschaftspolitik'],['federal_nl','federal_fr'])
    historical=[
      ('justitie','Justitie','Justice','Justiz','Justitie'),
      ('financien','Financiën','Finances','Finanzen','Financiën'),
      ('binnenland','Binnenlandse Zaken','Intérieur','Inneres','Binnenlandse zaken'),
      ('buitenland','Buitenlandse Zaken, Buitenlandse Handel en Ontwikkelingssamenwerking','Affaires étrangères, du Commerce extérieur et de la Coopération au Développement','Auswärtige Angelegenheiten, Außenhandel und Entwicklungszusammenarbeit','Buitenlandse zaken en ontwikkelingssamenwerking'),
      ('economie','Economische Zaken','Affaires économiques','Wirtschaftsangelegenheiten','Economie'),
      ('landbouw','Middenstand en Landbouw','Classes moyennes et de l’Agriculture','Mittelstand und Landwirtschaft','Landbouw en middenstand'),
      ('arbeid','Tewerkstelling en Arbeid','Emploi et du Travail','Beschäftigung und Arbeit','Werk en sociaal overleg'),
      ('sociaal','Sociale Zaken, Volksgezondheid en Leefmilieu','Affaires sociales, de la Santé publique et de l’Environnement','Soziale Angelegenheiten, Volksgesundheit und Umwelt','Sociale zaken, volksgezondheid en leefmilieu'),
      ('verkeer','Verkeer en Infrastructuur','Communications et de l’Infrastructure','Verkehr und Infrastruktur','Mobiliteit en infrastructuur'),
      ('ambtenaren','Ambtenarenzaken','Fonction publique','Öffentlicher Dienst','Algemeen bestuur'),
    ]
    for key,nl,fr,de,domain in historical:
        french={'justitie':'de la Justice','financien':'des Finances','binnenland':'de l’Intérieur','buitenland':'des Affaires étrangères, du Commerce extérieur et de la Coopération au Développement','economie':'des Affaires économiques','landbouw':'des Classes moyennes et de l’Agriculture','arbeid':'de l’Emploi et du Travail','sociaal':'des Affaires sociales, de la Santé publique et de l’Environnement','verkeer':'des Communications et de l’Infrastructure','ambtenaren':'de la Fonction publique'}
        german={'justitie':'der Justiz','financien':'der Finanzen','binnenland':'des Innern'}
        add('ministerie_'+key,'Ministerie van '+nl,domain,['Ministerie van '+nl,'Ministère '+french[key],'Ministerium '+german.get(key,'für '+de)],['history'],historical=True)
    for key,name,aliases,domain in [
      ('personeel','Personeel en Organisatie',['Service public fédéral Personnel et Organisation'],'Algemeen bestuur'),
      ('budget','Budget en Beheerscontrole',['Service public fédéral Budget et Contrôle de la Gestion'],'Financiën en begroting'),
      ('fedict','Informatie- en Communicatietechnologie',['Service public fédéral Technologie de l’Information et de la Communication'],'Digitalisering')]:
        add('historisch_fod_'+key,'FOD '+name,domain,['Federale Overheidsdienst '+name]+aliases,['federal_nl','federal_fr'],historical=True)
    regional=[
      ('vlaamse_overheid','Vlaamse overheid',['Vlaamse overheid'],'vlaanderen'),
      ('spw','Service public de Wallonie',['Service public de Wallonie','Waalse Overheidsdienst','Öffentlicher Dienst der Wallonie'],'wallonie'),
      ('gob','Gewestelijke Overheidsdienst Brussel',['Gewestelijke Overheidsdienst Brussel','Service public régional de Bruxelles'],'bruxelles'),
      ('cfwb','Ministerie van de Franse Gemeenschap',['Ministerie van de Franse Gemeenschap','Ministère de la Communauté française'],'cfwb'),
      ('dg','Ministerie van de Duitstalige Gemeenschap',['Ministerie van de Duitstalige Gemeenschap','Ministère de la Communauté germanophone','Ministerium der Deutschsprachigen Gemeinschaft'],'dg'),
    ]
    for key,name,aliases,source in regional:add(key,name,'Onbekend',aliases,[source])
    governments=[
      ('vlaamse_regering','Vlaamse Regering',['Vlaamse Regering','Gouvernement flamand','Flämische Regierung'],'vlaamse_regering'),
      ('waalse_regering','Waalse Regering',['Waalse Regering','Gouvernement wallon','Wallonische Regierung'],'cfwb'),
      ('brusselse_regering','Brusselse Hoofdstedelijke Regering',['Brusselse Hoofdstedelijke Regering','Regering van het Brussels Hoofdstedelijk Gewest','Gouvernement de la Région de Bruxelles-Capitale'],'bruxelles'),
      ('franse_regering','Regering van de Franse Gemeenschap',['Regering van de Franse Gemeenschap','Gouvernement de la Communauté française'],'cfwb'),
      ('duitse_regering','Regering van de Duitstalige Gemeenschap',['Regering van de Duitstalige Gemeenschap','Gouvernement de la Communauté germanophone','Regierung der Deutschsprachigen Gemeinschaft'],'dg'),
      ('ggc_college','Verenigd College van de Gemeenschappelijke Gemeenschapscommissie',['Verenigd College van de Gemeenschappelijke Gemeenschapscommissie','Collège réuni de la Commission communautaire commune'],'ggc'),
    ]
    for key,name,aliases,source in governments:add(key,name,'Onbekend',aliases,[source],kind='regering')
    for key,nl,domain in [('financien','Financiën en Begroting','Financiën en begroting'),('onderwijs','Onderwijs en Vorming','Onderwijs en vorming'),('zorg','Zorg','Welzijn en volksgezondheid'),('omgeving','Omgeving','Omgeving'),('mobiliteit','Mobiliteit en Openbare Werken','Mobiliteit en openbare werken'),('cultuur','Cultuur, Jeugd en Media','Cultuur, jeugd en media')]:
        add('vl_'+key,'Departement '+nl,domain,['Departement '+nl],['vlaanderen'])
    for key,name,domain in [('finances','Finances','Financiën'),('mobilite','Mobilité et Infrastructures','Mobiliteit en infrastructuur'),('agriculture','Agriculture, Ressources naturelles et Environnement','Landbouw en leefmilieu'),('territoire','Territoire, Logement, Patrimoine, Énergie','Ruimte, wonen, erfgoed en energie'),('interieur','Intérieur et Action sociale','Binnenlands bestuur en sociale zaken'),('economie','Économie, Emploi, Recherche','Economie, werk en onderzoek')]:
        add('spw_'+key,'SPW '+name,domain,['SPW '+name,'Service public de Wallonie '+name],['wallonie'])
    return rows


def folded(value):
    """Accenten/case/witruimte normaliseren met verwijzing naar originele posities."""
    chars=[];positions=[]
    for index,char in enumerate(value):
        for c in unicodedata.normalize('NFKD',char).casefold():
            if unicodedata.combining(c):continue
            c="'" if c in '’‘' else ' ' if c.isspace() else c
            if c==' ' and chars and chars[-1]==' ':continue
            chars.append(c);positions.append(index)
    return ''.join(chars),positions


REFERENCE=reference_list()
ALIASES=sorted([(folded(alias)[0],row) for row in REFERENCE for alias in row['aliases']],key=lambda item:-len(item[0]))
# Stop vóór juridische inhoud, aanhef van de Koning, motiveringen of een verslag.
BODY=re.compile(r'(?:gelet op|vu (?:la|le|les|l\x27)|considerant|artikel\s*\d|article\s*(?:\d|unique)|art\.\s*\d|albert ii|filip,|philippe,|baudouin,|boudewijn,|verslag aan|rapport au|advies van|avis du)(?=\W|$)')


def identify(prefix):
    """Alleen een expliciete hoofding of benoemde uitgever helemaal aan het begin.

    Niet een naam in een artikel, citaat, handtekening of advies herkennen.
    Meerdere onafhankelijke organisaties: Onbekend, kandidaten blijven bewaard.
    """
    unknown={'orgaan':'Onbekend','beleidsdomein':'Onbekend','authority_id':None,'status':'geen_herkende_hoofding','evidence':[]}
    if not prefix:return {**unknown,'status':'tekst_ontbreekt'}
    normalized,positions=folded(prefix[:4096])
    if re.search(r'bijlagen\s+\d+\s+tot\s+\d+.{0,80}teksten',normalized[:1200]):
        return {**unknown,'status':'samengestelde_publicatie'}
    cutoff=BODY.search(normalized)
    end=cutoff.start() if cutoff else len(normalized)
    candidates=[]
    for alias,row in ALIASES:
        for match in re.finditer(re.escape(alias),normalized[:end]):
            a,b=match.span()
            if a and normalized[a-1].isalnum():continue
            if b<len(normalized) and normalized[b].isalpha():continue
            before=normalized[:a].strip();after=normalized[b:end].lstrip()
            original=prefix[positions[a]:positions[b-1]+1]
            # Een expliciet benoemde uitgever: 'De Vlaamse Regering,Gelet ...'.
            issuer=row['kind']=='regering' and before in ('','de','het','le','la','der','die','das') and (not after or after.startswith((',',':')))
            # Afzonderlijke hoofding, vaak zonder spatie aan datum vastgeplakt.
            tail=prefix[positions[b-1]+1:]
            heading=row['kind']!='regering' and (original.isupper() or not before or before in ('bron:','source:','quelle:')) and (
                bool(re.match(r'\s*\d{1,2}[ .]',tail)) or bool(re.match(r'[ \t]*\r?\n',tail)) or
                bool(re.match(r'\s+(?:EN|ET|UND|&)\s+(?:FEDERALE OVERHEIDSDIENST|SERVICE PUBLIC|F[ÖO]DERALER|MINISTERIUM|MINISTERIE|MINIST[ÈE]RE)',tail)) or not tail.strip())
            if issuer or heading:candidates.append({'row':row,'start':positions[a],'end':positions[b-1]+1,'text':original,'method':'expliciete_uitgever' if issuer else 'hoofding'})
    # Een specifieke dienstnaam heeft voorrang op de daarin vervatte algemene naam.
    candidates=[c for c in candidates if not any(o['start']<=c['start'] and o['end']>=c['end'] and o['end']-o['start']>c['end']-c['start'] for o in candidates)]
    unique={c['row']['id'] for c in candidates}
    evidence=[{k:c[k] for k in ('start','end','text','method')}|{'authority_id':c['row']['id']} for c in candidates]
    if len(unique)!=1:return {**unknown,'status':'meerdere_organen' if unique else unknown['status'],'evidence':evidence}
    row=candidates[0]['row']
    return {'orgaan':row['orgaan'],'beleidsdomein':row['beleidsdomein'],'authority_id':row['id'],'status':'gekoppeld','evidence':evidence}
