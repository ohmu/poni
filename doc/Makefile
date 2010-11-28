docs= 
s5=
style=style.css
dot=

all: $(docs) $(s5) $(dot) 

clean: 
	rm -rf $(docs) $(s5) ui/ $(dot)

$(s5): %.html: %.rst
	rst2s5.py $< $@

$(docs): %.html: %.rst $(style)
	rst2html.py --stylesheet-path=$(style) $< $@

build-dep:
	apt-get install --yes python-docutils

$(dot): %.png: %.dot
	dot -Tpng -o$@ $<

