#!/usr/bin/env python3

import os
import filecmp
import fnmatch
import glob
import regex
import se
import lxml.cssselect
import lxml.etree as etree

def get_unused_selectors(se_root_directory):
	try:
		with open(os.path.join(se_root_directory, "src", "epub", "css", "local.css"), encoding="utf-8") as file:
			css = file.read()

	except Exception:
		raise FileNotFoundError("Couldn't open {}".format(os.path.join(se_root_directory, "src", "epub", "css", "local.css")))

	# Remove actual content of css selectors
	css = regex.sub(r"{[^}]+}", "", css, flags=regex.MULTILINE)

	# Remove trailing commas
	css = regex.sub(r",", "", css)

	# Remove comments
	css = regex.sub(r"/\*.+?\*/", "", css, flags=regex.DOTALL)

	# Remove @ defines
	css = regex.sub(r"^@.+", "", css, flags=regex.MULTILINE)

	# Construct a dictionary of selectors
	selectors = set([line for line in css.splitlines() if line != ""])
	unused_selectors = set(selectors)

	# Get a list of .xhtml files to search
	filenames = glob.glob(os.path.join(se_root_directory, "src", "epub", "text") + os.sep + "*.xhtml")

	# Now iterate over each CSS selector and see if it's used in any of the files we found
	for selector in selectors:
		try:
			sel = lxml.cssselect.CSSSelector(selector, translator="html", namespaces=se.XHTML_NAMESPACES)
		except lxml.cssselect.ExpressionError:
			# This gets thrown if we use pseudo-elements, which lxml doesn't support
			unused_selectors.remove(selector)
			continue

		for filename in filenames:
			if not filename.endswith("titlepage.xhtml") and not filename.endswith("imprint.xhtml") and not filename.endswith("uncopyright.xhtml"):
				# We have to remove the default namespace declaration from our document, otherwise
				# xpath won't find anything at all.  See http://stackoverflow.com/questions/297239/why-doesnt-xpath-work-when-processing-an-xhtml-document-with-lxml-in-python
				with open(filename, "r") as file:
					xhtml = file.read().replace(" xmlns=\"http://www.w3.org/1999/xhtml\"", "")

				tree = etree.fromstring(str.encode(xhtml))
				if tree.xpath(sel.path, namespaces=se.XHTML_NAMESPACES):
					unused_selectors.remove(selector)
					break

	return unused_selectors

def lint(se_root_directory, tools_root_directory):
	if not os.path.isdir(se_root_directory):
		raise NotADirectoryError("Not a directory")

	messages = []

	license_file_path = os.path.join(tools_root_directory, "templates", "LICENSE.md")
	core_css_file_path = os.path.join(tools_root_directory, "templates", "core.css")
	logo_svg_file_path = os.path.join(tools_root_directory, "templates", "logo.svg")
	uncopyright_file_path = os.path.join(tools_root_directory, "templates", "uncopyright.xhtml")

	with open(os.path.join(se_root_directory, "src", "epub", "content.opf"), "r+", encoding="utf-8") as file:
		metadata_xhtml = file.read()

	# Get the ebook language, for later use
	language = regex.search(r"<dc:language>([^>]+?)</dc:language>", metadata_xhtml).group(1)

	# Check local.css for various items, for later use
	abbr_elements = []
	with open(os.path.join(se_root_directory, "src", "epub", "css", "local.css"), "r", encoding="utf-8") as file:
		css = file.read()

		local_css_has_subtitle_style = "span[epub|type~=\"subtitle\"]" in css

		abbr_styles = regex.findall(r"abbr\.[a-z]+", css)

	# Check if there are non-typogrified quotes or em-dashes in metadata descriptions
	if regex.search(r"<meta id=\"long-description\" property=\"se:long-description\" refines=\"#description\">[^<]+?(['\"]|\-\-)[^<]+?</meta>", metadata_xhtml) is not None:
		messages.append("Non-typogrified \", ', or -- detected in metadata long description")

	if regex.search(r"<dc:description id=\"description\">[^<]+?(['\"]|\-\-)[^<]+?</meta>", metadata_xhtml) is not None:
		messages.append("Non-typogrified \", ', or -- detected in metadata dc:description")

	#Check for HTML entities in long-description
	if regex.search(r"&amp;[a-z]+?;", metadata_xhtml):
		messages.append("HTML entites detected in metadata.  Use Unicode equivalents instead")

	# Check for illegal em-dashes in <dc:subject>
	if regex.search(r"<dc:subject id=\"[^\"]+?\">[^<]+?—[^<]+?</meta>", metadata_xhtml) is not None:
		messages.append("Illegal em-dash detected in dc:subject; use --")

	# Check for correct external URLs
	if "http://www.gutenberg.org" in metadata_xhtml:
		messages.append("Non-https gutenberg.org link in content.opf")

	if "http://catalog.hathitrust.org" in metadata_xhtml:
		messages.append("Non-https hathitrust.org link in content.opf")

	if "http://archive.org" in metadata_xhtml:
		messages.append("Non-https archive.org link in content.opf")

	if regex.search(r"id\.loc\.gov/authorities/names/[^\.]+\.html", metadata_xhtml):
		messages.append("id.loc.gov URL ending with .html in content.opf; remove ending .html")

	# Make sure some static files are unchanged
	if not filecmp.cmp(license_file_path, os.path.join(se_root_directory, "LICENSE.md")):
		messages.append("LICENSE.md does not match {}".format(license_file_path))

	if not filecmp.cmp(core_css_file_path, os.path.join(se_root_directory, "src", "epub", "css", "core.css")):
		messages.append("core.css does not match {}".format(core_css_file_path))

	if not filecmp.cmp(logo_svg_file_path, os.path.join(se_root_directory, "src", "epub", "images", "logo.svg")):
		messages.append("logo.svg does not match {}".format(logo_svg_file_path))

	if not filecmp.cmp(uncopyright_file_path, os.path.join(se_root_directory, "src", "epub", "text", "uncopyright.xhtml")):
		messages.append("uncopyright.xhtml does not match {}".format(uncopyright_file_path))

	# Check for unused selectors
	unused_selectors = get_unused_selectors(se_root_directory)
	if unused_selectors:
		messages.append("Unused CSS selectors in local.css:")
		for selector in unused_selectors:
			messages.append(" {}".format(selector))

	# Now iterate over individual files for some checks
	for root, _, filenames in os.walk(se_root_directory):
		for filename in fnmatch.filter(filenames, "*.xhtml"):
			with open(os.path.join(root, filename), "r", encoding="utf-8") as file:
				xhtml = file.read()

				# Check for non-https links
				if "http://www.gutenberg.org" in xhtml:
					messages.append("Non-https gutenberg.org link in {}".format(filename))

				if "http://catalog.hathitrust.org" in xhtml:
					messages.append("Non-https hathitrust.org link in {}".format(filename))

				if "http://archive.org" in xhtml:
					messages.append("Non-https archive.org link in {}".format(filename))

				# Check for empty <p> tags
				if "<p/>" in xhtml or "<p></p>" in xhtml:
					messages.append("Empty <p/> tag in {}".format(filename))

				# Check for missing subtitle styling
				if "epub:type=\"subtitle\"" in xhtml and not local_css_has_subtitle_style:
					messages.append("Subtitles detected, but no subtitle style detected in local.css. File: {}".format(filename))

				# Did someone use colons instead of dots for SE identifiers? e.g. se:name:vessel:ship
				matches = regex.findall(r"\bse:[a-z]+:(?:[a-z]+:?)*", xhtml)
				if matches:
					messages.append("Illegal colon (:) detected in SE identifier.  SE identifiers are separated by dots (.) not colons (:). Identifier: {} File: {}".format(matches, filename))

				# Collect abbr elements for later check
				result = regex.findall("<abbr[^<]+?>", xhtml)
				result = [item.replace("eoc", "").replace(" \"", "").strip() for item in result]
				abbr_elements = list(set(result + abbr_elements))

				# Check if language tags in individual files match the language in content.opf
				if filename not in se.IGNORED_FILES:
					file_language = regex.search(r"<html[^<]+xml\:lang=\"([^\"]+)\"", xhtml).group(1)
					if language != file_language:
						messages.append("{} language is {}, but content.opf language is {}".format(filename, file_language, language))

			# Check for missing MARC relators
			if filename == "introduction.xhtml" and ">aui<" not in metadata_xhtml and ">win<" not in metadata_xhtml:
				messages.append("introduction.xhtml found, but no MARC relator 'aui' (Author of introduction, but not the chief author) or 'win' (Writer of introduction)")

			if filename == "preface.xhtml" and ">wpr<" not in metadata_xhtml:
				messages.append("preface.xhtml found, but no MARC relator 'wpr' (Writer of preface)")

			if filename == "afterword.xhtml" and ">aft<" not in metadata_xhtml:
				messages.append("afterword.xhtml found, but no MARC relator 'aft' (Author of colophon, afterword, etc.)")

			if filename == "endnotes.xhtml" and ">ann<" not in metadata_xhtml:
				messages.append("endnotes.xhtml found, but no MARC relator 'ann' (Annotator)")

			if filename == "loi.xhtml" and ">ill<" not in metadata_xhtml:
				messages.append("loi.xhtml found, but no MARC relator 'ill' (Illustrator)")

	for element in abbr_elements:
		try:
			css_class = regex.search(r"class=\"([^\"]+?)\"", element).group(1)
		except Exception:
			continue
		if css_class and (css_class == "name" or css_class == "temperature") and "abbr." + css_class not in abbr_styles:
			messages.append("abbr.{} element found, but no style in local.css".format(css_class))

	return messages