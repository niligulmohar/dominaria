#! /usr/bin/env python

import csv, datetime, getpass, io, optparse, sys
import deckbox.http

######################################################################

def main():
    (options, filenames) = parse_arguments()

    collection = Collection()

    add_files_by_name_to_collection(filenames, collection)

    if options.tradelist_file:
        add_tradecounts_to_collection(open(options.tradelist_file), collection)

    if options.deckbox_import:
        if options.deckbox_password:
            password = options.deckbox_password
        else:
            password = getpass.getpass("Password for %s: " % options.deckbox_user)
        session = deckbox.http.DeckboxSession(login=options.deckbox_user,
                                              password=password,
                                              debug=False)
        old_inventory = session.get_inventory_csv_export_for_username(options.deckbox_user)
        now = datetime.datetime.now()
        with open(now.strftime("deckbox-inventory-backup-%Y%m%d-%H%M%S.csv"), "w") as backup:
            backup.write(old_inventory)

        if not options.tradelist_file:
            add_tradecounts_to_collection(io.StringIO(old_inventory), collection)

        outfile = io.StringIO()
        write_collection_to_file(collection, outfile)
        session.update_inventory(outfile.getvalue())

    if options.output_file or not options.deckbox_import:
        filename = options.output_file or "output.csv"
        with open(filename, "w") as outfile:
            write_collection_to_file(collection, outfile)

######################################################################

def parse_arguments():
    parser = optparse.OptionParser()
    parser.add_option("-o", "--output-file", dest="output_file",
                      help="write output to FILE", metavar="FILE")
    parser.add_option("-t", "--tradelist-file", dest="tradelist_file",
                      help="add tradelist counts from FILE", metavar="FILE")
    parser.add_option("-d", "--deckbox-import", dest="deckbox_import",
                      help="import collection to Deckbox while preserving tradecounts", action="store_true")
    parser.add_option("-u", "--deckbox-user", dest="deckbox_user",
                      help="Deckbox username", metavar="USERNAME")
    parser.add_option("-p", "--deckbox-password", dest="deckbox_password",
                      help="Deckbox password, necessary when importing", metavar="PASSWORD")

    return parser.parse_args()

def add_files_by_name_to_collection(filenames, collection):
    for filename in filenames:
        with open(filename) as infile:
            add_file_to_collection(infile, collection)

def add_file_to_collection(infile, collection):
    reader = get_reader_for_file(infile)
    reader.add_cards_to_collection(collection)

def add_tradecounts_to_collection(infile, collection):
    reader = get_reader_for_file(infile)
    reader.add_tradecounts_to_collection(collection)

def write_collection_to_file(collection, outfile):
    writer = DeckboxWriter(outfile)
    writer.write_collection(collection)

######################################################################

def get_reader_for_file(file):
    line = file.readline()
    if line.startswith("Count,Tradelist Count,Name"):
        file.seek(0)
        return DeckboxReader(file)
    elif line.startswith("Total Qty,Reg Qty,Foil Qty,Card"):
        file.seek(0)
        return DeckedBuilderReader(file)

class CollectionReader(object):
    def add_cards_to_collection(self, collection):
        for card in self.cards():
            collection.add_card(card)
    def add_tradecounts_to_collection(self, collection):
        for card in self.cards():
            collection.add_tradecount(card)

class DeckedBuilderReader(CollectionReader):
    def __init__(self, infile):
        self.reader = csv.reader(infile)
    def cards(self):
        header = next(self.reader)
        for line in self.reader:
            regular, foiled, name, edition = line[1:5]
            regular = int(regular)
            foiled = int(foiled)
            if regular > 0:
                card = Card(count = regular, name = name, edition = edition)
                yield card
            if foiled > 0:
                card = Card(count = foiled, name = name, edition = edition, foil = True)
                yield card

class DeckboxReader(CollectionReader):
    def __init__(self, infile):
        self.reader = csv.reader(infile)
    def cards(self):
        header = next(self.reader)
        count_index = header.index("Count")
        tradelist_count_index = header.index("Tradelist Count")
        name_index = header.index("Name")
        foil_index = header.index("Foil")
        textless_index = header.index("Textless")
        promo_index = header.index("Promo")
        signed_index = header.index("Signed")
        edition_index = header.index("Edition")
        condition_index = header.index("Condition")
        language_index = header.index("Language")

        for line in self.reader:
            if len(line) == 0:
                continue
            count = int(line[count_index])
            tradelist_count = int(line[tradelist_count_index])
            name = line[name_index]
            foil = line[foil_index] != ""
            textless = line[textless_index] != ""
            promo = line[promo_index] != ""
            signed = line[signed_index] != ""
            edition = line[edition_index]
            condition = line[condition_index]
            language = line[language_index]

            card = Card(count = count,
                        tradelist_count = tradelist_count,
                        name = name,
                        foil = foil,
                        textless = textless,
                        promo = promo,
                        signed = signed,
                        edition = edition,
                        condition = condition,
                        language = language)

            yield card

class DeckboxWriter(object):
    def __init__(self, outfile):
        self.writer = csv.writer(outfile)
    def write_collection(self, collection):
        self.writer.writerow(("Count",
                              "Tradelist Count",
                              "Name",
                              "Foil",
                              "Textless",
                              "Promo",
                              "Signed",
                              "Edition",
                              "Condition",
                              "Language"))
        for card in collection.sorted_cards():
            self.writer.writerow((card.count,
                                  card.tradelist_count,
                                  card.name,
                                  card.foil and "foil" or "",
                                  card.textless and "textless" or "",
                                  card.promo and "promo" or "",
                                  card.signed and "signed" or "",
                                  card.edition,
                                  card.condition,
                                  card.language))

######################################################################

class Collection(object):
    def __init__(self):
        self.cards = {}
    def add_card(self, card):
        key = card.key();
        if key in self.cards:
            self.cards[key].count += card.count
        else:
            self.cards[key] = card
    def add_tradecount(self, other_card):
        key = other_card.key();
        if key in self.cards:
            card = self.cards[key]
            card.tradelist_count += other_card.tradelist_count
            card.tradelist_count = min(card.count, card.tradelist_count)
    def sorted_cards(self):
        for key in sorted(self.cards.keys()):
            yield self.cards[key]

class Card(object):
    def __init__(self,
                 name,
                 edition,
                 count = 0,
                 tradelist_count = 0,
                 foil = False,
                 textless = False,
                 promo = False,
                 signed = False,
                 condition = "Near Mint",
                 language = "English"):
        self.count = count
        self.tradelist_count = tradelist_count
        self.name = name
        self.foil = foil
        self.textless = textless
        self.promo = promo
        self.signed = signed
        self.edition = edition
        self.condition = condition
        self.language = language
    def key(self):
        return "%s,%s,%s,%s,%s,%s,%s,%s\n" % (self.quoted_name(),
                                              self.foil,
                                              self.textless,
                                              self.promo,
                                              self.signed,
                                              self.edition,
                                              self.condition,
                                              self.language)
    def quoted_name(self):
        return '"%s"' % self.name

######################################################################

if __name__ == '__main__':
    main()

