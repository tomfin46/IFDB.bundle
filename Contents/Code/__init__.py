import re

# URLS
IFDB_BASE_URL = 'https://ifdb.fanedit.org/'
IFDB_BASE_SEARCH_URL = IFDB_BASE_URL + 'fanedit-search/search-results/'
IFDB_SEARCH_URL = IFDB_BASE_SEARCH_URL + '?query=%s&scope=title&keywords=%s&order=alpha'
IFDB_MOVIE_INFO_URL = IFDB_BASE_URL + '?p=%s'

REQUEST_DELAY = 0       # Delay used when requesting HTML, may be good to have to prevent being banned from the site
INITIAL_SCORE = 100     # Starting value for score before deductions are taken.
GOOD_SCORE = 98         # Score required to short-circuit matching and stop searching.
IGNORE_SCORE = 45       # Any score lower than this will be ignored.

SHORTEN_TITLES_MAP = {
    'sw': [
        ["Star Wars", "SW"],
        ["Episode", "Ep"]
        ],
    'lotr': [
        ["The Lord of the Rings", "LotR"],
        ["Lord of the Rings, The", "LotR"],
        ["Lord of the Rings", "LotR"]
        ]
    }

VERSION = '1.0.3'

def Start():
    HTTP.CacheTime = CACHE_1WEEK

class IFDBAgent(Agent.Movies):

  name = 'Internet Fanedit Database'
  languages = [Locale.Language.English]
  primary_provider = True
  #accepts_from = ['com.plexapp.agents.localmedia', 'com.plexapp.agents.thetvdb']
  accepts_from = ['com.plexapp.agents.localmedia', 'com.plexapp.agents.themoviedb']
  #contributes_to = ['com.plexapp.agents.thetvdb']
  
  ##### If logging pref turned on, output log message #####
  def Log(self, message, *args):
        if Prefs['debug']:
            Log(message, *args)

  ##### For using css class for xpath query in situations where multiple classes for a tag or trailing whitespace #####
  def getCssSearchAttr(self, className):
      return 'contains(concat(" ", normalize-space(@class), " "), " ' + className + ' ")'

  ##### Return result of xpath query as string #####
  def getStringContentFromXPath(self, source, query):
        return source.xpath('string(' + query + ')')

  ##### Pull out standard string fieldValue using xpath #####
  def getFieldValue(self, source, fieldName):
      return self.getStringContentFromXPath(source, './/div[' + self.getCssSearchAttr(fieldName) + ']/div[' + self.getCssSearchAttr("jrFieldValue") + ']/a[text()]')

  ##### Pull out fieldValue that's a list using xpath #####
  def getFieldValueList(self, source, fieldName):
      return source.xpath('.//div[' + self.getCssSearchAttr(fieldName) + ']/div[' + self.getCssSearchAttr("jrFieldValue") + ']//li')

  ##### Format titles based on key pased in #####
  def titleFormat(self, key, title):
      for pair in SHORTEN_TITLES_MAP[key]:
          pattern = re.compile(pair[0], re.IGNORECASE)
          title = pattern.sub(pair[1], title)

      return title

  ##### Check for phrases to shorten in fanedit title (this one is used for the results screen to avoid streams of incomprehensible Star Wars Episode.... entries #####
  def shortenTitle(self, title):
       if "star wars" in title.lower():
           title = self.titleFormat('sw', title)
       elif "lord of the rings" in title.lower():
           title = self.titleFormat('lotr', title)

       return title

  ##### If preference set to shorten certain titles (Star Wars, Lord of the Rings) then shorten #####
  def changeTitleIfPrefered(self, title):
       if Prefs['shortensw'] and "star wars" in title.lower():
           return self.titleFormat('sw', title)
       elif Prefs['shortenlotr'] and "lord of the rings" in title.lower():
           return self.titleFormat('lotr', title)

       return title

  ##### Carry out search #####
  def doSearch(self, url):
      self.Log("###########  Doing Search  ###########")
      self.Log("For Url: %s", url)

      # Fetch HTML
      html = HTML.ElementFromURL(url, sleep=REQUEST_DELAY)
      found = []

      title = self.getStringContentFromXPath(html, '//h1[' + self.getCssSearchAttr("contentheading") + ']/span[@itemprop="headline"]/text()')
      self.Log("Title: %s", title)

      if len(title) != 0:
          # This means we got an exact match and have been redirected to the actual fanedit's page so we need to do some ugly stuff to pull out the id so it can be used in update method
          # Cleanest way is to pull out the id from the fanedits compare checkbox button
          compareBtns = html.xpath('//input[' + self.getCssSearchAttr("jrCheckListing") + ']')
          pattern = re.compile('listing', re.IGNORECASE)
          id = pattern.sub('', self.getStringContentFromXPath(compareBtns[0], './@data-listingid'))

          self.Log("Id found for %s: %s", title, id)

          title = self.shortenTitle(title)

          date = self.getFieldValue(html, 'jrFaneditreleasedate')
          thumb = self.getStringContentFromXPath(html, './/div[' + self.getCssSearchAttr("jrListingMainImage") + ']//img/@src')

          found.append({
              'id': id,
              'title': title,
              'thumb': thumb,
              'date': date
              })

      else:
          results = html.xpath('//div[' + self.getCssSearchAttr("jrListItem") + ']')

          self.Log("%u results found", len(results))

          for r in results:
              title = self.getStringContentFromXPath(r, './/div[' + self.getCssSearchAttr("jrContentTitle") + ']/a[text()]')

              self.Log("Title of result: %s", title)

              title = self.shortenTitle(title)

              id = r.xpath('.//div[' + self.getCssSearchAttr("jrContentTitle") + ']/a/@id')[0].replace('jr-listing-title-', '')
              thumb = self.getStringContentFromXPath(r, './/div[' + self.getCssSearchAttr("jrListingThumbnail") + ']/a/img/@src')
              date = self.getFieldValue(r, 'jrFaneditreleasedate')

              found.append({
                  'id': id,
                  'title': title,
                  'thumb': thumb,
                  'date': date
                  })

      return found

  ##############################
  ##### Main Search Method #####
  ##############################

  def search(self, results, media, lang, manual):

      self.Log("Version of agent: %s", VERSION)

      if media.year and int(media.year) > 1900:
          year = media.year
      else:
          year = ''

      self.Log("Search for: %s", media.name)

      # Strip Diacritics from media name
      stripped_name = String.StripDiacritics(media.name)
      if len(stripped_name) == 0:
          stripped_name = media.name

      searchUrl = IFDB_SEARCH_URL % ('all', String.Quote((stripped_name).encode('utf-8'), usePlus=True))

      # Do the Search
      found = self.doSearch(searchUrl)

      if len(found) == 0:
            self.Log('No results found for query "%s"%s', stripped_name, year)
            return

      info = []
      # For each result calculate Levenshtein Distance from our query
      for f in found:
          score = INITIAL_SCORE - abs(String.LevenshteinDistance(f['title'].lower(), media.name.lower()))

          if score >= IGNORE_SCORE:
              f['score'] = score
              info.append(f)

      # Reverse sort by score so most likely match is at the top
      info = sorted(info, key=lambda inf: inf['score'], reverse=True)

      for i in info:
          results.Append(MetadataSearchResult(id = i['id'], name  = i['title'] + ' [' + str(i['date']) + ']', score = i['score'], thumb = i['thumb'], lang = lang))

          # If more than one result but current match is considered a good score use this and move on
          if not manual and len(info) > 1 and i['score'] >= GOOD_SCORE:
                break

  #############################
  ##### Main Update Methd #####
  #############################

  def update(self, metadata, media, lang):

      url = IFDB_MOVIE_INFO_URL % metadata.id

      try:
            # Fetch HTML
            html = HTML.ElementFromURL(url, sleep=REQUEST_DELAY)

            # Title
            title = self.getStringContentFromXPath(html, '//h1[' + self.getCssSearchAttr("contentheading") + ']/span[@itemprop="name"]/text()')
            metadata.title = self.changeTitleIfPrefered(title)

            # Rating
            rating = self.getStringContentFromXPath(html, '//span[' + self.getCssSearchAttr("jrRatingValue") + ']/span[1]')
            if rating == '(0)':
                rating = 0.0
            metadata.rating = float(rating)

            # Faneditor Name
            metadata.directors.clear()
            metadata.directors.add(self.getFieldValue(html, 'jrFaneditorname'))

            # Tagline
            metadata.tagline = self.getFieldValue(html, 'jrTagline')

            # Original Movie Titles
            original_title = self.getFieldValue(html, 'jrOriginalmovietitle')
            if len(original_title) == 0:
                orig_titles = []
                titles = self.getFieldValueList(html, 'jrOriginalmovietitle')
                for t in titles:
                    orig_titles.append(self.getStringContentFromXPath(t, './a[text()]'))

                metadata.original_title = ', '.join(orig_titles)
            else:
                metadata.original_title = original_title

            # Genres
            genre = self.getFieldValue(html, 'jrGenre')
            if len(genre) == 0:
                genres = self.getFieldValueList(html, 'jrGenre')
                for g in genres:
                    gen = self.getStringContentFromXPath(g, './a[text()]')
                    metadata.genres.add(gen)
            else:
                metadata.genres.add(genre)

            # Franchises
            franchise = self.getFieldValue(html, 'jrFranchise')
            if len(franchise) == 0:
                franchises = self.getFieldValueList(html, 'jrFranchise')
                for f in franchises:
                    fran = self.getStringContentFromXPath(f, './a[text()]')
                    metadata.collections.add(fran)
            else:
                metadata.collections.add(franchise)

            # Fanedit Type
            fanedit_type = self.getFieldValue(html, 'jrFanedittype')
            if len(fanedit_type) == 0:
                types = self.getFieldValueList(html, 'jrFanedittype')
                for t in types:
                    type = self.getStringContentFromXPath(t, './a[text()]')
                    metadata.tags.add(type)
            else:
                metadata.tags.add(fanedit_type)

            # Release Date
            year = self.getFieldValue(html, 'jrFaneditreleasedate')
            pattern = re.compile(r'[^\d]+', re.IGNORECASE)
            metadata.year = int(pattern.sub('', year))

            # Brief Synopsis
            metadata.summary = self.getStringContentFromXPath(html, './/div[' + self.getCssSearchAttr("jrBriefsynopsis") + ']/div[' + self.getCssSearchAttr("jrFieldValue") + ']')

            # Poster
            poster_url = self.getStringContentFromXPath(html, './/div[' + self.getCssSearchAttr("jrListingMainImage") + ']//img/@src')

            if poster_url not in metadata.posters:
                try:
                    metadata.posters[poster_url] = Proxy.Media(HTTP.Request(poster_url).content)
                except: pass


      except Exception, e:
            Log.Error('Error obtaining data for item with id %s (%s) [%s] ', metadata.id, url, e.message)
