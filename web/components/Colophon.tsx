import Link from "next/link";

export function Colophon() {
  return (
    <footer className="colophon">
      <p>
        Pulsar, студенческая команда ВМК МГУ, конкурс «Академия Финтеха 2026», трек ВТБ. Демо на публичных текстах с удалёнными
        персональными данными и на синтетике. Проверка по тексту письма, не гарантия и не юридическая консультация.
      </p>
      <p>
        Нормы и сроки: <a href="https://www.cbr.ru/StaticHtml/File/155903/mrp.pdf" rel="noopener">методичка Банка России для предпринимателей (PDF)</a>,
        письма Банка России <a href="https://www.cbr.ru/Crosscut/LawActs/File/10079" rel="noopener">ИН&#8209;01&#8209;59/98</a> и{" "}
        <a href="https://cbr.ru/Crosscut/LawActs/File/12160" rel="noopener">ИН&#8209;03&#8209;59/11</a>, 115&#8209;ФЗ и 161&#8209;ФЗ в редакции от 04.08.2026.
      </p>
      <p>
        <Link href="/politika/">Политика обработки персональных данных</Link>
      </p>
    </footer>
  );
}
