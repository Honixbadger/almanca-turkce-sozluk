import { assignFreshIds } from "./tree-utils.js";

const baseStates = () => ({ hover: {}, focus: {} });

const registry = [
  {
    type: "section",
    label: "Bölüm",
    group: "Yerleşim",
    description: "Genel amaçlı blok konteyneri.",
    container: true,
    icon: "▣",
    blueprint: {
      type: "section",
      props: { title: "Bölüm", text: "Kısa açıklama", visible: true, align: "left" },
      style: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        padding: "20px",
        margin: "0 0 16px 0",
        backgroundColor: "#ffffff",
        borderRadius: "20px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "rgba(18, 34, 28, 0.08)",
        boxShadow: "0 16px 32px rgba(20, 32, 27, 0.08)"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "navbar",
    label: "Navbar",
    group: "Yerleşim",
    description: "Üst gezinme alanı.",
    container: true,
    icon: "≡",
    blueprint: {
      type: "navbar",
      props: { title: "Sözlük", items: "Ana Sayfa,Favoriler,Ayarlar", visible: true, align: "space-between" },
      style: {
        display: "flex",
        flexDirection: "row",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "12px",
        padding: "16px 20px",
        margin: "0 0 16px 0",
        backgroundColor: "#18382f",
        textColor: "#ffffff",
        borderRadius: "18px"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "sidebar",
    label: "Sidebar",
    group: "Yerleşim",
    description: "Dikey filtre veya menü alanı.",
    container: true,
    icon: "▤",
    blueprint: {
      type: "sidebar",
      props: { title: "Filtreler", text: "Kategori, kaynak ve görünüm kontrolleri", visible: true, align: "left" },
      style: {
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        padding: "18px",
        backgroundColor: "#f0f5ef",
        borderRadius: "18px",
        minWidth: "220px"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "card",
    label: "Kart",
    group: "Temel",
    description: "İçerik kartı.",
    container: true,
    icon: "□",
    blueprint: {
      type: "card",
      props: { title: "Kart Başlığı", text: "Kart açıklaması", visible: true, align: "left" },
      style: {
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        padding: "18px",
        backgroundColor: "#ffffff",
        borderRadius: "18px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "rgba(18, 34, 28, 0.08)"
      },
      states: {
        hover: { boxShadow: "0 16px 34px rgba(23, 43, 36, 0.12)" },
        focus: {}
      },
      children: []
    }
  },
  {
    type: "heading",
    label: "Başlık",
    group: "Temel",
    description: "H1-H4 arası başlık.",
    container: false,
    icon: "H",
    blueprint: {
      type: "heading",
      props: { text: "Başlık metni", level: "2", visible: true, align: "left" },
      style: {
        fontSize: "32px",
        fontWeight: "700",
        textColor: "#17352d",
        margin: "0"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "text",
    label: "Metin",
    group: "Temel",
    description: "Açıklama paragrafı.",
    container: false,
    icon: "¶",
    blueprint: {
      type: "text",
      props: { text: "Açıklayıcı metin", visible: true, align: "left" },
      style: {
        fontSize: "16px",
        fontWeight: "400",
        textColor: "#54675d",
        margin: "0"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "button",
    label: "Buton",
    group: "Temel",
    description: "Tıklanabilir aksiyon düğmesi.",
    container: false,
    icon: "◉",
    blueprint: {
      type: "button",
      props: { text: "Buton", icon: "", visible: true, align: "center" },
      style: {
        padding: "12px 18px",
        backgroundColor: "#1c6a58",
        textColor: "#ffffff",
        borderRadius: "12px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "#1c6a58",
        fontWeight: "600"
      },
      states: {
        hover: { backgroundColor: "#114f41", borderColor: "#114f41" },
        focus: { boxShadow: "0 0 0 3px rgba(28, 106, 88, 0.18)" }
      },
      children: []
    }
  },
  {
    type: "favorite-button",
    label: "Favori Butonu",
    group: "Sözlük",
    description: "Kaydet / favori aksiyonu.",
    container: false,
    icon: "★",
    blueprint: {
      type: "favorite-button",
      props: { text: "Favorilere Ekle", icon: "★", visible: true, align: "center" },
      style: {
        padding: "10px 16px",
        backgroundColor: "#fff3df",
        textColor: "#8b5b20",
        borderRadius: "999px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "#e6c999",
        fontWeight: "600"
      },
      states: {
        hover: { backgroundColor: "#ffe8bf" },
        focus: {}
      },
      children: []
    }
  },
  {
    type: "input",
    label: "Input",
    group: "Form",
    description: "Tek satırlı giriş alanı.",
    container: false,
    icon: "⌨",
    blueprint: {
      type: "input",
      props: { placeholder: "Metin gir", text: "", visible: true, align: "left" },
      style: {
        width: "100%",
        padding: "12px 14px",
        backgroundColor: "#ffffff",
        borderRadius: "12px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "#ccd8d1"
      },
      states: {
        hover: { borderColor: "#8fb5aa" },
        focus: { borderColor: "#1c6a58", boxShadow: "0 0 0 3px rgba(28, 106, 88, 0.12)" }
      },
      children: []
    }
  },
  {
    type: "search-box",
    label: "Arama Kutusu",
    group: "Sözlük",
    description: "Input ve aksiyon butonundan oluşan arama alanı.",
    container: false,
    icon: "⌕",
    blueprint: {
      type: "search-box",
      props: { placeholder: "Kelime ara", buttonText: "Ara", visible: true, align: "stretch" },
      style: {
        display: "flex",
        flexDirection: "row",
        gap: "10px",
        padding: "14px",
        backgroundColor: "#ffffff",
        borderRadius: "18px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "rgba(18, 34, 28, 0.08)"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "list",
    label: "Liste",
    group: "Temel",
    description: "Çok satırlı liste alanı.",
    container: false,
    icon: "☰",
    blueprint: {
      type: "list",
      props: { title: "Liste", items: "Birinci öğe,İkinci öğe,Üçüncü öğe", visible: true, align: "left" },
      style: {
        padding: "14px",
        backgroundColor: "#ffffff",
        borderRadius: "16px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "rgba(18, 34, 28, 0.08)"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "chip-row",
    label: "Etiket Satırı",
    group: "Sözlük",
    description: "Chip / tag gösterimi.",
    container: false,
    icon: "⌗",
    blueprint: {
      type: "chip-row",
      props: { items: "otomotiv,teknik,öncelikli", visible: true, align: "left" },
      style: {
        display: "flex",
        gap: "8px",
        flexWrap: "wrap"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "modal",
    label: "Modal",
    group: "Yerleşim",
    description: "Üst katman önizleme penceresi.",
    container: true,
    icon: "◫",
    blueprint: {
      type: "modal",
      props: { title: "Modal Başlığı", text: "Bilgi metni", visible: true, align: "center" },
      style: {
        padding: "22px",
        backgroundColor: "rgba(17, 27, 23, 0.72)",
        borderRadius: "22px",
        minHeight: "280px"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "word-card",
    label: "Kelime Kartı",
    group: "Sözlük",
    description: "Kelime detayını gösteren domain bileşeni.",
    container: true,
    icon: "W",
    blueprint: {
      type: "word-card",
      props: {
        word: "das Automatikgetriebe",
        translation: "otomatik şanzıman",
        meta: "isim • otomotiv • doğrulandı",
        visible: true,
        align: "left"
      },
      style: {
        display: "flex",
        flexDirection: "column",
        gap: "14px",
        padding: "22px",
        backgroundColor: "#ffffff",
        borderRadius: "22px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "rgba(18, 34, 28, 0.08)"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "meaning-block",
    label: "Anlam Alanı",
    group: "Sözlük",
    description: "Tanım veya açıklama alanı.",
    container: false,
    icon: "≣",
    blueprint: {
      type: "meaning-block",
      props: { title: "Kısa bilgi", text: "Kelimenin anlamı burada görünür.", visible: true, align: "left" },
      style: {
        padding: "16px",
        backgroundColor: "#f4f7f2",
        borderRadius: "16px"
      },
      states: baseStates(),
      children: []
    }
  },
  {
    type: "example-block",
    label: "Örnek Cümle",
    group: "Sözlük",
    description: "Almanca ve Türkçe örnek cümle kutusu.",
    container: false,
    icon: "❝",
    blueprint: {
      type: "example-block",
      props: {
        german: "Das Automatikgetriebe schaltet weich.",
        turkish: "Otomatik şanzıman yumuşak geçiş yapar.",
        visible: true,
        align: "left"
      },
      style: {
        padding: "16px",
        backgroundColor: "#f8faf7",
        borderRadius: "16px",
        borderWidth: "1px",
        borderStyle: "solid",
        borderColor: "rgba(18, 34, 28, 0.08)"
      },
      states: baseStates(),
      children: []
    }
  }
];

export const COMPONENT_DEFINITIONS = registry;
export const COMPONENT_MAP = Object.fromEntries(registry.map((item) => [item.type, item]));

export function createComponent(type) {
  const definition = COMPONENT_MAP[type];
  if (!definition) {
    throw new Error(`Bilinmeyen bileşen: ${type}`);
  }
  return assignFreshIds(definition.blueprint);
}

export function getDefaultRoot() {
  return {
    id: "page-root",
    type: "page",
    props: { title: "Yeni Düzen", visible: true },
    style: {
      display: "flex",
      flexDirection: "column",
      gap: "18px",
      minHeight: "100%",
      padding: "12px"
    },
    states: { hover: {}, focus: {} },
    children: []
  };
}
