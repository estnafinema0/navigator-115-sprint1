#!/bin/zsh
# usage: x2t_params.sh in.pptx out.pdf   (R7-Office x2t; font list of the installed R7-Office desktop app)
IN=${1:a}; OUT=${2:a}
X2T_DIR=${X2T_DIR:-/Applications/R7-Office.app/Contents/Resources/converter}
FONTS=${R7_ALLFONTS:-$HOME/Library/Application Support/ru.nkt.r7-office-signature/data/fonts/AllFonts.js}
TMP=$(mktemp -d)
mkdir -p $TMP/x2ttmp
cat > $TMP/params.xml <<XML
<?xml version="1.0" encoding="utf-8"?>
<TaskQueueDataConvert xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
<m_sFileFrom>$IN</m_sFileFrom>
<m_sFileTo>$OUT</m_sFileTo>
<m_nFormatTo>513</m_nFormatTo>
<m_sAllFontsPath>$FONTS</m_sAllFontsPath>
<m_sTempDir>$TMP/x2ttmp</m_sTempDir>
<m_bIsNoBase64>false</m_bIsNoBase64>
</TaskQueueDataConvert>
XML
cd $X2T_DIR && ./x2t $TMP/params.xml
RC=$?
rm -rf $TMP
exit $RC
