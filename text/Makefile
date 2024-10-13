NAME=thesis
ABSTRACT=abstract
LATEXMKOPTS=-pdf #enable for forcing pdflatex
LATEXMK=latexmk $(LATEXMKOPTS)


all: attachment.tar.gz attachment.zip
	$(LATEXMK) $(NAME)
	$(LATEXMK) $(ABSTRACT)-cz
	$(LATEXMK) $(ABSTRACT)-en

clean:
	$(LATEXMK) -C
	rm -f attachment.tar.gz
	rm attachment.zip

attachment.tar.gz:
	tar -h -c -z -f attachment.tar.gz -C attachment .

attachment.zip:
	cd attachment; zip -r ../attachment.zip *
