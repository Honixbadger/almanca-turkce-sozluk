import { createComponent, getDefaultRoot } from "./component-library.js";

function setProps(node, props = {}) {
  node.props = { ...(node.props || {}), ...props };
  return node;
}

function setStyle(node, style = {}) {
  node.style = { ...(node.style || {}), ...style };
  return node;
}

function buildModel(name, children) {
  return {
    meta: {
      version: 1,
      name,
      updatedAt: new Date().toISOString()
    },
    root: {
      ...getDefaultRoot(),
      props: { title: name, visible: true },
      children
    }
  };
}

function heading(text, level = "1") {
  return setProps(createComponent("heading"), { text, level });
}

function paragraph(text) {
  return setProps(createComponent("text"), { text });
}

function card(titleText, bodyText) {
  return setStyle(
    setProps(createComponent("card"), { title: titleText, text: bodyText }),
    { gap: "12px" }
  );
}

function searchBox() {
  return setProps(createComponent("search-box"), {
    placeholder: "Almanca, Türkçe veya not ara",
    buttonText: "Ara"
  });
}

function favoritesTemplate() {
  const navbar = setProps(createComponent("navbar"), { title: "Favoriler", items: "Ana Sayfa,Favoriler,Geçmiş" });
  const hero = setStyle(createComponent("section"), { backgroundColor: "#18382f" });
  hero.children.push(
    setStyle(setProps(createComponent("heading"), { text: "Sık kullandığın kelimeler", level: "1" }), { textColor: "#ffffff" }),
    setStyle(setProps(createComponent("text"), { text: "Favori listen, hızlı erişim için burada." }), { textColor: "rgba(255,255,255,0.78)" })
  );
  const chips = setProps(createComponent("chip-row"), { items: "favori,öğrenilecek,tekrar et" });
  const listCard = card("Kaydedilenler", "İstediğin kelimeleri daha sonra tekrar düzenleyebilirsin.");
  listCard.children.push(chips, setProps(createComponent("list"), { items: "Kupplung,Automatikgetriebe,Getriebesteuerung" }));
  return buildModel("Favoriler Sayfası", [navbar, hero, listCard]);
}

export const TEMPLATES = [
  {
    id: "home",
    name: "Ana Sayfa",
    description: "Başlık, arama ve öne çıkan bloklardan oluşan giriş ekranı.",
    build() {
      const navbar = setProps(createComponent("navbar"), { title: "Almanca-Türkçe Sözlük", items: "Ana Sayfa,Detay,Favoriler" });
      const hero = createComponent("section");
      hero.children.push(
        heading("Kelimeyi hızlı bul, detayı temiz gör.", "1"),
        paragraph("Arama, filtre ve öneri alanlarını tek ekranda kontrol et."),
        searchBox()
      );

      const highlights = setStyle(createComponent("section"), {
        display: "grid",
        gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
        gap: "14px",
        backgroundColor: "transparent",
        borderColor: "transparent",
        boxShadow: "none",
        padding: "0"
      });
      highlights.children.push(
        card("Toplam Kayıt", "12.480 kelime"),
        card("Son Güncelleme", "Bugün 14:20"),
        card("Hızlı Erişim", "Favoriler ve son aramalar")
      );

      return buildModel("Ana Sayfa", [navbar, hero, highlights]);
    }
  },
  {
    id: "detail",
    name: "Kelime Detay Sayfası",
    description: "Kelime kartı, anlam, etiket ve örnek cümle alanları hazır gelir.",
    build() {
      const navbar = setProps(createComponent("navbar"), { title: "Kelime Detayı", items: "Ara,Kaynaklar,Favoriler" });
      const wordCard = createComponent("word-card");
      wordCard.children.push(
        setProps(createComponent("chip-row"), { items: "isim,otomotiv,doğrulandı" }),
        createComponent("meaning-block"),
        createComponent("example-block")
      );
      return buildModel("Kelime Detay Sayfası", [navbar, wordCard]);
    }
  },
  {
    id: "results",
    name: "Arama Sonuçları",
    description: "Arama kutusu, sol listeler ve sağ detay alanı düzeni.",
    build() {
      const navbar = setProps(createComponent("navbar"), { title: "Arama Sonuçları", items: "Kelime,Filtre,Kaynak" });
      const search = searchBox();
      const layout = setStyle(createComponent("section"), {
        display: "grid",
        gridTemplateColumns: "320px 1fr",
        gap: "16px"
      });
      const sidebar = createComponent("sidebar");
      sidebar.children.push(setProps(createComponent("list"), { title: "Sonuçlar", items: "Getriebe,Automatikgetriebe,Kupplung" }));
      const detail = createComponent("word-card");
      detail.children.push(createComponent("meaning-block"), createComponent("example-block"));
      layout.children.push(sidebar, detail);
      return buildModel("Arama Sonuçları Sayfası", [navbar, search, layout]);
    }
  },
  {
    id: "favorites",
    name: "Favoriler Sayfası",
    description: "Favori kelimeleri ve etiketleri bir arada gösteren liste ekranı.",
    build: favoritesTemplate
  }
];

export function createInitialModel() {
  return TEMPLATES[0].build();
}
