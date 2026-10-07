interface ISiteMetadataResult {
  siteTitle: string;
  siteUrl: string;
  description: string;
  logo: string;
  navLinks: {
    name: string;
    url: string;
  }[];
}

const data: ISiteMetadataResult = {
  siteTitle: 'lircOS Running',
  siteUrl: 'https://lirc0618.github.io/running_page/',
  logo: 'https://github.com/lirc0618.png',
  description: 'lircOS 的跑步记录',
  navLinks: [
    {
      name: 'GitHub',
      url: 'https://github.com/lirc0618',
    },
  ],
};

export default data;
