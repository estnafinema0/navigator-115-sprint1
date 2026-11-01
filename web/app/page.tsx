import Link from "next/link";
import { ArrowSign, BarSign } from "@/components/Signs";

export default function Landing() {
  return (
    <>
      <section className="hero" aria-labelledby="h1">
        <div className="sign sign-hero">
          <h1 id="h1">Счёт ограничили по 115&#8209;ФЗ? Покажем, что это за мера, какие пути открыты и куда жаловаться бесполезно.</h1>
          <p className="lead">
            Вставьте текст уведомления или запроса банка. Навигатор покажет меру, норму, ближайший срок и допустимые маршруты.
            Каждое поле стоит на цитате из письма.
          </p>
          <div className="cta-row">
            <Link className="btn btn-primary" href="/razbor/">
              Разобрать письмо банка
            </Link>
            <Link className="btn btn-ghost" href="/razbor/?sample=A1">
              Пример: отказ в операции
            </Link>
          </div>
        </div>
        <div className="hero-side">
          <p className="evidence">
            Путь обжалования вне банка назван в 1 из 45 публичных уведомлений банков; МВК при Банке России не упомянута ни разу.
            <sup>
              <a href="#fn1" id="fnref1" aria-label="Сноска 1: источник цифр">
                1
              </a>
            </sup>
          </p>
          <h2 className="side-title">МВК рассматривает только четыре вида решений</h2>
          <p className="side-src">
            Методичка Банка России, с. 18. Остальные меры обжалуются другими путями: в самом банке, в Банке России, в суде.
          </p>
          <ul className="post" aria-label="Что обжалуется в МВК, а что нет">
            <li className="ok"><ArrowSign /><span>Отказ в операции (п.&nbsp;11 ст.&nbsp;7)</span></li>
            <li className="ok"><ArrowSign /><span>Отказ в заключении договора (п.&nbsp;5.2 ст.&nbsp;7)</span></li>
            <li className="ok"><ArrowSign /><span>Меры при высоком риске (п.&nbsp;5 ст.&nbsp;7.7)</span></li>
            <li className="ok"><ArrowSign /><span>Отказ Банка России пересмотреть высокий риск</span></li>
            <li className="no"><BarSign /><span>Ограничение интернет-банка, блокировка карты, «жёлтый» риск, меры по 161&#8209;ФЗ: в этот перечень не входят</span></li>
          </ul>
        </div>
      </section>

      <section className="section route-section" aria-labelledby="h-route">
        <div className="route-grid">
          <div>
            <h2 id="h-route">Одно письмо, три остановки</h2>
            <p>Всё считает сервер команды по нормам с датой редакции. Модель только находит поля в тексте, и у каждого поля есть цитата.</p>
          </div>
          <ol className="vline">
            <li>
              <Link href="/razbor/" className="vstop">
                <span className="dot" aria-hidden="true" />
                <span>
                  <b>Письмо и карточка</b>
                  Мера, норма, причина, что запросили, срок и канал. Чего банк не указал, видно сразу.
                </span>
              </Link>
            </li>
            <li>
              <Link href="/marshrut/" className="vstop">
                <span className="dot" aria-hidden="true" />
                <span>
                  <b>Сроки и маршрут</b>
                  Законные сроки по производственному календарю и пути обжалования именно для вашей меры.
                </span>
              </Link>
            </li>
            <li>
              <Link href="/zayavlenie/" className="vstop">
                <span className="dot" aria-hidden="true" />
                <span>
                  <b>Заявление</b>
                  Шаблон Банка России, заполненный фактами вашего дела. Доводы вы пишете сами.
                </span>
              </Link>
            </li>
          </ol>
        </div>
      </section>

      <section className="section bank-section" aria-labelledby="h-bank">
        <p className="big-figure">
          0&nbsp;из&nbsp;45
          <sup>
            <a href="#fn1" aria-label="Сноска 1: источник цифр">
              1
            </a>
          </sup>
        </p>
        <div>
          <h2 id="h-bank">Для банка: страж уведомлений</h2>
          <p>
            Ни один из 45 публичных текстов уведомлений и запросов не содержит сразу норму закона, срок, порядок действий и путь
            обжалования, которых требуют письма Банка России ИН&#8209;01&#8209;59/98 и ИН&#8209;03&#8209;59/11. Страж проверяет уведомление
            до отправки клиенту и отмечает то, что раскрывать нельзя (п.&nbsp;6 ст.&nbsp;7 115&#8209;ФЗ).
          </p>
          <Link className="btn btn-quiet" href="/strazh/">
            Проверить уведомление
          </Link>
        </div>
      </section>

      <section id="granica" className="section" aria-labelledby="h-granica">
        <h2 id="h-granica">Границы сервиса</h2>
        <p>
          Навигатор работает по открытым нормам и шаблонам Банка России и проверяет только текст, который вы вставили. Маршруты
          показывают, куда обращаться допустимо по закону. Это не юридическая консультация и не гарантия результата.
        </p>
        <ul className="post bounds" aria-label="Чего сервис не делает">
          <li className="no"><BarSign /><span>Не подсказывает, как обойти проверку банка</span></li>
          <li className="no"><BarSign /><span>Не меняет назначение платежей и не сочиняет пояснения</span></li>
          <li className="no"><BarSign /><span>Не обещает разблокировку</span></li>
          <li className="no"><BarSign /><span>Не отправляет текст во внешние сервисы: модель работает на сервере команды</span></li>
        </ul>
        <p id="fn1" className="footnote">
          <sup>1</sup> Корпус Pulsar: предварительная выборка 45 публичных текстов уведомлений и запросов банков (отзывы, форумы,
          публикации юристов, с 2007 по 2026 год), один кодировщик, не аудит банков. Отчёт воспроизводится командой{" "}
          <code>make corpus-stats</code>.{" "}
          <a href="#fnref1" aria-label="Вернуться к тексту">
            Вернуться к тексту
          </a>
        </p>
      </section>
    </>
  );
}
